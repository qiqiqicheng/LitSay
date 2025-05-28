import os
import json
import pandas as pd
from flask import request, jsonify, current_app, g, make_response
from werkzeug.utils import secure_filename
import traceback
import uuid

from . import upload_bp
from app.db import query_db, get_db, close_db
from app.utils.decorators import login_required

# 确保 OPTIONS 处理器在路由顶部定义，并且正确处理预检请求
@upload_bp.route('/<path:path>', methods=['OPTIONS'])
@upload_bp.route('/', methods=['OPTIONS'])
def handle_options_request(*args, **kwargs):
    """处理所有OPTIONS请求"""
    print(f"处理OPTIONS请求: path={kwargs.get('path', '/')} args={args}")
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Max-Age', '3600')  # 缓存预检响应1小时
    response.status_code = 200
    return response

# 确保/metadata路由也能处理OPTIONS请求
@upload_bp.route('/metadata', methods=['OPTIONS'])
def metadata_options():
    """专门处理/metadata的OPTIONS请求"""
    print("处理/metadata OPTIONS请求")
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
    response.status_code = 200
    return response

@upload_bp.route('/metadata-only', methods=['POST'])
@login_required
def save_metadata_only():
    user_id = g.current_user['user_id']
    data = request.json

    # 增加调试日志
    print(f"[save_metadata_only] 收到请求 - user_id={user_id}")
    print(f"[save_metadata_only] 请求数据: {data}")

    if not data:
        print("warning:[save_metadata_only] 请求体为空")
        return jsonify({"error": "参数错误", "message": "请求缺少必要参数"}), 400

    folder_id = data.get('folderId')
    metadata_list = data.get('metadataList', [])

    print(f"[save_metadata_only] folderId={folder_id}, metadataList类型={type(metadata_list)}, 长度={len(metadata_list)}")

    if not folder_id:
        print("warning:[save_metadata_only] 没有提供folderId")
        return jsonify({"error": "参数错误", "message": "必须提供文件夹ID"}), 400

    # 尝试将folder_id转为int
    try:
        folder_id_int = int(folder_id)
        print(f"[save_metadata_only] folderId转换成功: {folder_id_int}")
    except Exception as e:
        current_app.logger.error(f"[save_metadata_only] folderId转换失败: {folder_id}, 错误: {e}")
        return jsonify({"error": "参数错误", "message": "文件夹ID必须为数字"}), 400

    if not isinstance(metadata_list, list) or len(metadata_list) == 0:
        print("[save_metadata_only] metadataList不是有效的数组或为空")
        return jsonify({"error": "参数错误", "message": "必须提供元数据列表"}), 400

    # 检查文件夹是否存在且属于当前用户
    folder = query_db("""
        SELECT directory_id FROM directory
        WHERE directory_id = %s AND user_id = %s
    """, (folder_id_int, user_id), one=True)

    if not folder:
        print(f"==db:[save_metadata_only] 找不到文件夹或权限不足: folderId={folder_id_int}, user_id={user_id}")
        return jsonify({"error": "参数错误", "message": "指定的文件夹不存在或无权访问"}), 404

    print(f"==db[save_metadata_only] 文件夹验证通过: {folder_id_int}, 开始处理{len(metadata_list)}个元数据项")

    # 处理上传的元数据
    document_ids = []
    file_names = []

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        print("==db[save_metadata_only] 成功获取数据库连接")
        
        for index, item in enumerate(metadata_list):
            file_name = item.get('fileName', 'unknown.pdf')
            metadata = item.get('metadata', {})
            
            print(f"[save_metadata_only] 处理第{index+1}项: file_name={file_name}")
            
            if not metadata or 'title' not in metadata:
                print(f"[save_metadata_only] 第{index+1}项缺少有效元数据或标题")
                continue
                
            try:
                conn.start_transaction()
                print(f"==db[save_metadata_only] 第{index+1}项: 开始事务")
                
                title = metadata.get('title')
                doi = metadata.get('doi')
                publish_date = metadata.get('publishDate')
                journal_name = metadata.get('journal')
                conference_name = metadata.get('conference')
                
                print(f"==db[save_metadata_only] 第{index+1}项: title={title}, doi={doi}, 出版日期={publish_date}, journal={journal_name}, conference={conference_name}")
                
                container_id = None
                if journal_name or conference_name:
                    container_type = 'journal' if journal_name else 'conference'
                    container_name = journal_name or conference_name
                    
                    print(f"[save_metadata_only] 第{index+1}项: 查询容器 type={container_type}, name={container_name}")
                    
                    cursor.execute("""
                        SELECT container_id FROM container
                        WHERE user_id = %s AND type = %s AND container_name = %s
                    """, (user_id, container_type, container_name))
                    
                    container_result = cursor.fetchone()
                    if container_result:
                        container_id = container_result['container_id']
                        print(f"[save_metadata_only] 第{index+1}项: 找到现有容器, id={container_id}")
                    else:
                        print(f"[save_metadata_only] 第{index+1}项: 创建新容器, type={container_type}, name={container_name}")
                        if container_type == 'journal':
                            cursor.execute("""
                                INSERT INTO container (user_id, type, container_name)
                                VALUES (%s, %s, %s)
                            """, (user_id, container_type, container_name))
                        else:
                            cursor.execute("""
                                INSERT INTO container (user_id, type, container_name)
                                VALUES (%s, %s, %s)
                            """, (user_id, container_type, container_name))
                        
                        container_id = cursor.lastrowid
                        print(f"[save_metadata_only] 第{index+1}项: 创建容器成功, id={container_id}")
                
                # 创建文档记录
                print(f"[save_metadata_only] 第{index+1}项: 插入文档记录 folder_id={folder_id_int}, container_id={container_id}")
                cursor.execute("""
                    INSERT INTO document (directory_id, container_id, user_id, title, doi, publication_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (folder_id_int, container_id, user_id, title, doi, publish_date))
                
                document_id = cursor.lastrowid
                print(f"[save_metadata_only] 第{index+1}项: 文档创建成功, id={document_id}")
                
                # 处理作者信息
                authors = metadata.get('authors', [])
                if isinstance(authors, list) and authors:
                    print(f"[save_metadata_only] 第{index+1}项: 处理{len(authors)}个作者")
                    for i, author_name in enumerate(authors):
                        if not author_name:
                            print(f"[save_metadata_only] 第{index+1}项: 跳过空作者名称")
                            continue
                        
                        # 获取作者相关信息
                        sequence = metadata.get('sequence', [])[i] if i < len(metadata.get('sequence', [])) else None
                        institution = metadata.get('institutions', [])[i] if i < len(metadata.get('institutions', [])) else None
                        location = metadata.get('institution_location', [])[i] if i < len(metadata.get('institution_location', [])) else None
                        email = metadata.get('email', [])[i] if i < len(metadata.get('email', [])) else None
                        
                        print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: name={author_name}, sequence={sequence}, institution={institution}")
                        
                        # 查找或创建作者
                        cursor.execute("""
                            SELECT author_id FROM author
                            WHERE user_id = %s AND author_name = %s
                        """, (user_id, author_name))
                        
                        author_result = cursor.fetchone()
                        if author_result:
                            author_id = author_result['author_id']
                            print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 找到现有作者 id={author_id}")
                        else:
                            cursor.execute("""
                                INSERT INTO author (user_id, author_name, author_email)
                                VALUES (%s, %s, %s)
                            """, (user_id, author_name, email))
                            author_id = cursor.lastrowid
                            print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建新作者 id={author_id}")
                        
                        # 确保sequence为标准值
                        if sequence not in ["first", "corresponding", "additional", "other"]:
                            print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: sequence值({sequence})不标准, 使用'additional'")
                            sequence = "additional"  # 默认为additional
                        
                        # # 创建文档-作者关联
                        # cursor.execute("""
                        #     INSERT INTO document_author (document_id, author_id, sequence)
                        #     VALUES (%s, %s, %s)
                        # """, (document_id, author_id, sequence))
                        # print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建文档-作者关联成功")
                        
                        # 处理机构信息
                        if institution:
                            cursor.execute("""
                                SELECT institution_id FROM institution
                                WHERE user_id = %s AND institution_name = %s
                            """, (user_id, institution))
                            
                            institution_result = cursor.fetchone()
                            if institution_result:
                                institution_id = institution_result['institution_id']
                                print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 找到现有机构 id={institution_id}")
                            else:
                                cursor.execute("""
                                    INSERT INTO institution (user_id, institution_name, institution_location)
                                    VALUES (%s, %s, %s)
                                """, (user_id, institution, location))
                                institution_id = cursor.lastrowid
                                print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建新机构 id={institution_id}")
                        
                            # 检查作者-机构关联是否已存在
                            cursor.execute("""
                                SELECT * FROM author_institution
                                WHERE author_id = %s AND institution_id = %s
                            """, (author_id, institution_id))
                            
                            existing_relation = cursor.fetchone()
                            
                            if existing_relation:
                                print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 作者-机构关联已存在")
                            else:
                                # 创建作者-机构关联
                                cursor.execute("""
                                    INSERT INTO author_institution (author_id, institution_id)
                                    VALUES (%s, %s)
                                """, (author_id, institution_id))
                                print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建作者-机构关联成功")
                            
                            # 创建文档id-作者id-机构id关联
                            cursor.execute("""
                                INSERT INTO document_author (document_id, author_id, institution_id, sequence)
                                VALUES (%s, %s, %s, %s)
                            """, (document_id, author_id, institution_id, sequence))
                            print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建文档-作者-机构关联成功")
                        else:
                            # 直接创建文档id-作者id关联，忽略机构id
                            cursor.execute("""
                                INSERT INTO document_author (document_id, author_id, institution_id, sequence)
                                VALUES (%s, %s, NULL, %s)
                            """, (document_id, author_id, sequence))
                            print(f"[save_metadata_only] 第{index+1}项, 作者{i+1}: 创建文档-作者关联成功，不含机构id")
                
                # 处理关键词信息
                keywords = metadata.get('keywords', [])
                if isinstance(keywords, list) and keywords:
                    print(f"[save_metadata_only] 第{index+1}项: 处理{len(keywords)}个关键词")
                    for keyword_idx, keyword in enumerate(keywords):
                        if not keyword:
                            print(f"[save_metadata_only] 第{index+1}项: 跳过空关键词")
                            continue
                        
                        cursor.execute("""
                            SELECT keyword_id FROM keyword
                            WHERE user_id = %s AND keyword_name = %s
                        """, (user_id, keyword))
                        
                        keyword_result = cursor.fetchone()
                        if keyword_result:
                            keyword_id = keyword_result['keyword_id']
                            print(f"[save_metadata_only] 第{index+1}项, 关键词{keyword_idx+1}: 找到现有关键词 '{keyword}' id={keyword_id}")
                        else:
                            cursor.execute("""
                                INSERT INTO keyword (user_id, keyword_name)
                                VALUES (%s, %s)
                            """, (user_id, keyword))
                            keyword_id = cursor.lastrowid
                            print(f"[save_metadata_only] 第{index+1}项, 关键词{keyword_idx+1}: 创建新关键词 '{keyword}' id={keyword_id}")
                        
                        # 创建文档-关键词关联
                        cursor.execute("""
                            INSERT INTO document_keyword (document_id, keyword_id)
                            VALUES (%s, %s)
                        """, (document_id, keyword_id))
                        print(f"[save_metadata_only] 第{index+1}项, 关键词{keyword_idx+1}: 创建文档-关键词关联成功")
                
                conn.commit()
                print(f"[save_metadata_only] 第{index+1}项: 事务已提交")
                
                # 记录成功处理的项目
                document_ids.append(document_id)
                file_names.append(file_name)
                current_app.logger.info(f"[save_metadata_only] 第{index+1}项: '{title}' 保存成功, document_id={document_id}")
                
            except Exception as e:
                conn.rollback()
                current_app.logger.error(f"[save_metadata_only] 第{index+1}项: 保存元数据失败: {e}")
                current_app.logger.error(f"[save_metadata_only] 详细错误: {traceback.format_exc()}")
    
    except Exception as e:
        current_app.logger.error(f"[save_metadata_only] 处理元数据列表总体失败: {e}")
        current_app.logger.error(f"[save_metadata_only] 详细错误: {traceback.format_exc()}")
        return jsonify({"error": "服务器错误", "message": f"保存元数据失败: {str(e)}"}), 500
    finally:
        close_db()
        print("[save_metadata_only] 数据库连接已关闭")
    
    if not document_ids:
        current_app.logger.warning("[save_metadata_only] 没有成功保存任何元数据记录")
        return jsonify({
            "code": 1,
            "message": "没有成功保存任何元数据记录",
            "data": { "importedCount": 0 }
        }), 400
    
    current_app.logger.info(f"[save_metadata_only] 成功保存 {len(document_ids)} 条元数据记录")
    return jsonify({
        "code": 0,
        "message": f"成功保存 {len(document_ids)} 条元数据记录",
        "data": {
            "docIds": document_ids,
            "fileNames": file_names,
            "importedCount": len(document_ids)
        }
    })

@upload_bp.route('/metadata', methods=['POST'])
@login_required
def upload_metadata():
    """批量导入元数据（前端已完成解析）"""
    try:
        print("\n==== 开始处理元数据批量导入请求 ====")
        data = request.json
        if not data:
            print("错误: 请求中未包含JSON数据")
            return jsonify({"error": "数据格式错误", "message": "请求中未包含JSON数据"}), 400
        
        # 获取必要参数
        metadata_list = data.get('metadataList', [])
        folder_id = data.get('folderId')
        user_id = g.current_user['user_id']
        
        print(f"收到请求参数: folder_id={folder_id}, user_id={user_id}")
        print(f"元数据列表长度: {len(metadata_list)}")
        
        if not metadata_list:
            print("错误: 元数据列表为空")
            return jsonify({"error": "数据格式错误", "message": "元数据列表为空"}), 400
        
        if not folder_id:
            print("错误: 未提供文件夹ID")
            return jsonify({"error": "参数错误", "message": "必须提供文件夹ID"}), 400
        
        current_app.logger.info(f"导入元数据，记录数: {len(metadata_list)}")
        print(f"导入元数据，记录数: {len(metadata_list)}")
        
        # 验证文件夹归属
        print(f"SQL: 验证文件夹归属 SELECT directory_id FROM directory WHERE directory_id = {folder_id} AND user_id = {user_id}")
        folder = query_db("SELECT directory_id FROM directory WHERE directory_id = %s AND user_id = %s", 
                         (folder_id, user_id), one=True)
        
        if not folder:
            print(f"错误: 文件夹不存在或无权访问, folder_id={folder_id}, user_id={user_id}")
            return jsonify({"error": "权限错误", "message": "文件夹不存在或无权访问"}), 404
        
        print(f"文件夹验证成功: {folder}")
        
        imported_count = 0
        failed_count = 0
        
        # 处理每条元数据记录
        for index, metadata in enumerate(metadata_list):
            try:
                print(f"\n---- 开始处理第 {index+1}/{len(metadata_list)} 条元数据 ----")
                print(f"元数据内容: {json.dumps(metadata, ensure_ascii=False)[:200]}...")
                
                # 从元数据中提取必要信息
                title = metadata.get('title')
                if not title:  # 跳过没有标题的记录
                    print(f"跳过记录 {index+1}: 缺少标题")
                    failed_count += 1
                    continue
                
                # 提取基本字段
                doi = metadata.get('doi')
                publish_date = metadata.get('publishDate')
                
                # 先处理容器（期刊/会议）
                container_id = None
                container_name = None
                container_type = None
                
                if metadata.get('journal'):
                    container_name = metadata.get('journal')
                    container_type = "journal"
                    journal_issue = metadata.get('journal_issue')
                    print(f"检测到期刊: {container_name}, issue: {journal_issue}")
                elif metadata.get('conference'):
                    container_name = metadata.get('conference')
                    container_type = "conference"
                    conference_time = metadata.get('conference_time')
                    conference_location = metadata.get('conference_location')
                    print(f"检测到会议: {container_name}, time: {conference_time}, location: {conference_location}")
                
                # 如果有容器信息，查找或创建容器
                if container_name and container_type:
                    print(f"处理容器信息: name={container_name}, type={container_type}")
                    
                    container_search_sql = "SELECT container_id FROM container WHERE container_name = %s AND user_id = %s AND type = %s"
                    print(f"SQL: 查找容器 - {container_search_sql}")
                    print(f"SQL参数: ({container_name}, {user_id}, {container_type})")
                    
                    container_result = query_db(
                        container_search_sql,
                        (container_name, user_id, container_type),
                        one=True
                    )
                    
                    if not container_result:
                        container_create_sql = """INSERT INTO container (container_name, user_id, type, journal_issue, 
                               conference_time, conference_location) 
                               VALUES (%s, %s, %s, %s, %s, %s)"""
                        
                        journal_issue = metadata.get('journal_issue') if container_type == "journal" else None
                        conference_time = metadata.get('conference_time') if container_type == "conference" else None
                        conference_location = metadata.get('conference_location') if container_type == "conference" else None
                        
                        print(f"SQL: 创建容器 - {container_create_sql}")
                        print(f"SQL参数: ({container_name}, {user_id}, {container_type}, {journal_issue}, {conference_time}, {conference_location})")
                        
                        container_id = query_db(
                            container_create_sql,
                            (container_name, user_id, container_type, 
                             journal_issue, conference_time, 
                             conference_location),
                            commit=True
                        )
                        print(f"容器创建成功，container_id = {container_id}")
                    else:
                        container_id = container_result['container_id']
                        print(f"找到现有容器，container_id = {container_id}")
                
                # 创建文档记录 - 更新插入语句，使用container_id
                insert_doc_sql = """INSERT INTO document 
                       (directory_id, user_id, title, doi, publication_date, container_id)
                       VALUES (%s, %s, %s, %s, %s, %s)"""
                
                print(f"SQL: 创建文档记录 - {insert_doc_sql}")
                print(f"SQL参数: ({folder_id}, {user_id}, {title}, {doi}, {publish_date}, {container_id})")
                
                document_id = query_db(
                    insert_doc_sql,
                    (folder_id, user_id, title, doi, publish_date, container_id),
                    commit=True
                )
                
                print(f"文档记录创建成功，document_id = {document_id}")
                
                # 处理作者 (如果存在)
                authors = metadata.get('authors', [])
                if isinstance(authors, list) and authors:
                    print(f"处理作者信息, 作者数: {len(authors)}")
                    for i, author_name in enumerate(authors):
                        if not author_name:
                            print(f"跳过空作者名，索引: {i}")
                            continue
                        
                        # 获取其他作者相关字段
                        sequence = metadata.get('sequence', [])[i] if i < len(metadata.get('sequence', [])) else "additional"
                        institution_name = metadata.get('institutions', [])[i] if i < len(metadata.get('institutions', [])) else None
                        location = metadata.get('institution_location', [])[i] if i < len(metadata.get('institution_location', [])) else None
                        email = metadata.get('email', [])[i] if i < len(metadata.get('email', [])) else None
                        
                        # 查找或创建作者 - 修改为同时更新邮箱
                        author_search_sql = "SELECT author_id FROM author WHERE author_name = %s AND user_id = %s"
                        print(f"SQL: 查找作者 - {author_search_sql}")
                        print(f"SQL参数: ({author_name}, {user_id})")
                        
                        author_id = query_db(
                            author_search_sql,
                            (author_name, user_id),
                            one=True
                        )
                        
                        if not author_id:
                            # 创建新作者，包含邮箱信息
                            author_create_sql = "INSERT INTO author (author_name, user_id, author_email) VALUES (%s, %s, %s)"
                            print(f"SQL: 创建作者(含邮箱) - {author_create_sql}")
                            print(f"SQL参数: ({author_name}, {user_id}, {email})")
                            
                            author_id = query_db(
                                author_create_sql,
                                (author_name, user_id, email),
                                commit=True
                            )
                            print(f"作者创建成功，author_id = {author_id}")
                        else:
                            author_id = author_id['author_id']
                            print(f"找到现有作者，author_id = {author_id}")
                            
                            # 如果有邮箱信息，更新现有作者的邮箱
                            if email:
                                author_update_sql = "UPDATE author SET author_email = %s WHERE author_id = %s AND user_id = %s"
                                print(f"SQL: 更新作者邮箱 - {author_update_sql}")
                                print(f"SQL参数: ({email}, {author_id}, {user_id})")
                                
                                query_db(
                                    author_update_sql,
                                    (email, author_id, user_id),
                                    commit=True
                                )
                                print(f"作者邮箱更新成功: email = {email}")
                        
                        # 查找或创建机构，获取机构ID
                        institution_id = None
                        if institution_name:
                            institution_search_sql = "SELECT institution_id, institution_location FROM institution WHERE institution_name = %s AND user_id = %s"
                            print(f"SQL: 查找机构 - {institution_search_sql}")
                            print(f"SQL参数: ({institution_name}, {user_id})")
                            
                            institution_result = query_db(
                                institution_search_sql,
                                (institution_name, user_id),
                                one=True
                            )
                            
                            if not institution_result:
                                # 创建新机构
                                institution_create_sql = "INSERT INTO institution (institution_name, institution_location, user_id) VALUES (%s, %s, %s)"
                                print(f"SQL: 创建机构 - {institution_create_sql}")
                                print(f"SQL参数: ({institution_name}, {location}, {user_id})")
                                
                                institution_id = query_db(
                                    institution_create_sql,
                                    (institution_name, location, user_id),
                                    commit=True
                                )
                                print(f"机构创建成功，institution_id = {institution_id}")
                            else:
                                institution_id = institution_result['institution_id']
                                print(f"找到现有机构，institution_id = {institution_id}")
                                
                                # 如果元数据中提供了新的地址信息，则更新机构地址
                                # location comes from metadata.get('institution_location', [])[i]
                                if location is not None: # Check if location is explicitly provided in input
                                    # Only update if the new location is different or if you always want to overwrite
                                    if location != institution_result.get('institution_location'):
                                        institution_update_sql = "UPDATE institution SET institution_location = %s WHERE institution_id = %s AND user_id = %s"
                                        print(f"SQL: 更新机构地址 - {institution_update_sql}")
                                        print(f"SQL参数: ({location}, {institution_id}, {user_id})")
                                        
                                        query_db(
                                            institution_update_sql,
                                            (location, institution_id, user_id),
                                            commit=True
                                        )
                                        print(f"机构地址更新成功: name='{institution_name}', new_location='{location}'")
                                    else:
                                        print(f"机构地址未改变: name='{institution_name}', location='{location}'")
                                else:
                                    print(f"未提供机构地址更新信息 for name='{institution_name}'")

                            # 检查作者-机构关联是否已存在，若不存在则添加
                            if institution_id and author_id:
                                # 查询是否已存在关联
                                author_institution_check_sql = """
                                SELECT 1 FROM author_institution 
                                WHERE author_id = %s AND institution_id = %s"""
                                print(f"SQL: 检查作者-机构关联 - {author_institution_check_sql}")
                                print(f"SQL参数: ({author_id}, {institution_id})")
                                
                                existing_relation = query_db(
                                    author_institution_check_sql,
                                    (author_id, institution_id),
                                    one=True
                                )
                                
                                # 如果关联不存在，创建新的关联
                                if not existing_relation:
                                    author_institution_sql = """
                                    INSERT INTO author_institution (author_id, institution_id) 
                                    VALUES (%s, %s)"""
                                    print(f"SQL: 创建作者-机构关联 - {author_institution_sql}")
                                    print(f"SQL参数: ({author_id}, {institution_id})")
                                    
                                    query_db(
                                        author_institution_sql,
                                        (author_id, institution_id),
                                        commit=True
                                    )
                                    print(f"作者-机构关联创建成功: author_id={author_id}, institution_id={institution_id}")
                                else:
                                    print(f"作者-机构关联已存在: author_id={author_id}, institution_id={institution_id}")
                        
                        print(f"作者 {i+1} ({author_name}) 详细信息: sequence={sequence}, institution_id={institution_id}, location={location}, email={email}")
                        
                        # 关联作者与文档 - 修改为不再传递email参数，因为email已存储在author表中
                        doc_author_sql = """INSERT INTO document_author 
                               (document_id, author_id, sequence, institution_id) 
                               VALUES (%s, %s, %s, %s)"""
                        
                        print(f"SQL: 关联作者与文档 - {doc_author_sql}")
                        print(f"SQL参数: ({document_id}, {author_id}, {sequence}, {institution_id})")
                        
                        query_db(
                            doc_author_sql,
                            (document_id, author_id, sequence, institution_id),
                            commit=True
                        )
                        print(f"作者 {author_name} 与文档关联成功")
                
                # 处理关键词 (如果存在)
                keywords = metadata.get('keywords', [])
                if isinstance(keywords, list) and keywords:
                    print(f"处理关键词信息, 关键词数: {len(keywords)}")
                    for keyword in keywords:
                        if not keyword:
                            print("跳过空关键词")
                            continue
                        
                        # 查找或创建关键词
                        keyword_search_sql = "SELECT keyword_id FROM keyword WHERE keyword_name = %s AND user_id = %s"
                        print(f"SQL: 查找关键词 - {keyword_search_sql}")
                        print(f"SQL参数: ({keyword}, {user_id})")
                        
                        keyword_id = query_db(
                            keyword_search_sql,
                            (keyword, user_id),
                            one=True
                        )
                        
                        if not keyword_id:
                            keyword_create_sql = "INSERT INTO keyword (keyword_name, user_id) VALUES (%s, %s)"
                            print(f"SQL: 创建关键词 - {keyword_create_sql}")
                            print(f"SQL参数: ({keyword}, {user_id})")
                            
                            keyword_id = query_db(
                                keyword_create_sql,
                                (keyword, user_id),
                                commit=True
                            )
                            print(f"关键词创建成功，keyword_id = {keyword_id}")
                        else:
                            keyword_id = keyword_id['keyword_id']
                            print(f"找到现有关键词，keyword_id = {keyword_id}")
                        
                        # 关联关键词与文档
                        doc_keyword_sql = "INSERT INTO document_keyword (document_id, keyword_id) VALUES (%s, %s)"
                        print(f"SQL: 关联关键词与文档 - {doc_keyword_sql}")
                        print(f"SQL参数: ({document_id}, {keyword_id})")
                        
                        query_db(
                            doc_keyword_sql,
                            (document_id, keyword_id),
                            commit=True
                        )
                        print(f"关键词 {keyword} 与文档关联成功")
                
                imported_count += 1
                print(f"---- 第 {index+1} 条元数据处理完成 ----")
                
            except Exception as e:
                print(f"处理第 {index+1} 条元数据时出错: {str(e)}")
                current_app.logger.error(f"导入元数据记录错误: {e}")
                failed_count += 1
                # 继续处理下一条记录
        
        print(f"\n==== 元数据批量导入完成 ====")
        print(f"成功导入: {imported_count} 条")
        print(f"导入失败: {failed_count} 条")
        
        if imported_count == 0:
            print("错误: 没有成功导入任何元数据记录")
            return jsonify({
                "code": 1,
                "message": "没有成功导入任何元数据记录",
                "data": {
                    "importedCount": 0,
                    "failedCount": failed_count
                }
            }), 400
        
        return jsonify({
            "code": 0,
            "message": f"成功导入 {imported_count} 条元数据记录",
            "data": {
                "importedCount": imported_count,
                "failedCount": failed_count
            }
        }), 200
        
    except Exception as e:
        print(f"批量导入元数据过程中发生异常: {str(e)}")
        current_app.logger.error(f"批量导入元数据失败: {e}")
        return jsonify({"error": "服务器错误", "message": f"处理元数据时出错: {str(e)}"}), 500