import os
import json
from flask import request, jsonify, current_app, g
from werkzeug.utils import secure_filename

from . import upload_bp
from app.db import query_db, get_db, close_db
from app.utils.decorators import login_required

@upload_bp.route('/metadata-only', methods=['POST'])
@login_required
def save_metadata_only():
    user_id = g.current_user['user_id']
    data = request.json
    
    if not data:
        return jsonify({"error": "参数错误", "message": "请求缺少必要参数"}), 400
    
    folder_id = data.get('folderId')
    metadata_list = data.get('metadataList', [])
    
    if not folder_id:
        return jsonify({"error": "参数错误", "message": "必须提供文件夹ID"}), 400
    
    if not metadata_list or not isinstance(metadata_list, list) or len(metadata_list) == 0:
        return jsonify({"error": "参数错误", "message": "必须提供元数据列表"}), 400
    
    # 检查文件夹是否存在且属于当前用户
    folder = query_db("""
        SELECT directory_id FROM directory
        WHERE directory_id = %s AND user_id = %s
    """, (folder_id, user_id), one=True)
    
    if not folder:
        return jsonify({"error": "参数错误", "message": "指定的文件夹不存在或无权访问"}), 404
    
    # 处理上传的元数据
    document_ids = []
    file_names = []
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        for item in metadata_list:
            file_name = item.get('fileName', 'unknown.pdf')
            metadata = item.get('metadata', {})
            
            if not metadata or 'title' not in metadata:
                continue
                
            try:
                conn.start_transaction()
                
                title = metadata.get('title')
                doi = metadata.get('doi')
                publish_date = metadata.get('publishDate')
                journal_name = metadata.get('journal')
                conference_name = metadata.get('conference')
                
                container_id = None
                if journal_name or conference_name:
                    container_type = 'journal' if journal_name else 'conference'
                    container_name = journal_name or conference_name
                    
                    cursor.execute("""
                        SELECT container_id FROM container
                        WHERE user_id = %s AND type = %s AND container_name = %s
                    """, (user_id, container_type, container_name))
                    
                    container_result = cursor.fetchone()
                    if container_result:
                        container_id = container_result['container_id']
                    else:
                        if container_type == 'journal':
                            # 为期刊添加默认的期号
                            cursor.execute("""
                                INSERT INTO container (user_id, type, container_name, journal_issue)
                                VALUES (%s, %s, %s, %s)
                            """, (user_id, container_type, container_name, "Vol. 1"))
                        else:
                            # 为会议添加默认的时间
                            cursor.execute("""
                                INSERT INTO container (user_id, type, container_name, conference_time)
                                VALUES (%s, %s, %s, %s)
                            """, (user_id, container_type, container_name, publish_date or "2023-01-01"))
                        
                        container_id = cursor.lastrowid
                
                # 创建文档记录（注意此处不包含文件路径）
                cursor.execute("""
                    INSERT INTO document (directory_id, container_id, user_id, title, doi, publication_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (folder_id, container_id, user_id, title, doi, publish_date))
                
                document_id = cursor.lastrowid
                
                # 处理作者信息
                authors = metadata.get('authors', [])
                if isinstance(authors, list) and authors:
                    for i, author_name in enumerate(authors):
                        if not author_name:
                            continue
                        
                        # 获取作者相关信息
                        sequence = metadata.get('sequence', [])[i] if i < len(metadata.get('sequence', [])) else None
                        institution = metadata.get('institutions', [])[i] if i < len(metadata.get('institutions', [])) else None
                        location = metadata.get('institution_location', [])[i] if i < len(metadata.get('institution_location', [])) else None
                        email = metadata.get('email', [])[i] if i < len(metadata.get('email', [])) else None
                        
                        # 查找或创建作者
                        cursor.execute("""
                            SELECT author_id FROM author
                            WHERE user_id = %s AND author_name = %s
                        """, (user_id, author_name))
                        
                        author_result = cursor.fetchone()
                        if author_result:
                            author_id = author_result['author_id']
                        else:
                            cursor.execute("""
                                INSERT INTO author (user_id, author_name, author_email)
                                VALUES (%s, %s, %s)
                            """, (user_id, author_name, email))
                            author_id = cursor.lastrowid
                        
                        # 确保sequence为标准值
                        if sequence not in ["first", "corresponding", "additional", "other"]:
                            sequence = "additional"  # 默认为additional
                        
                        # 创建文档-作者关联 - 直接使用字符串类型的sequence
                        cursor.execute("""
                            INSERT INTO document_author (document_id, author_id, sequence)
                            VALUES (%s, %s, %s)
                        """, (document_id, author_id, sequence))
                        
                        # 处理机构信息
                        if institution:
                            cursor.execute("""
                                SELECT institution_id FROM institution
                                WHERE user_id = %s AND institution_name = %s
                            """, (user_id, institution))
                            
                            institution_result = cursor.fetchone()
                            if institution_result:
                                institution_id = institution_result['institution_id']
                            else:
                                cursor.execute("""
                                    INSERT INTO institution (user_id, institution_name, institution_location)
                                    VALUES (%s, %s, %s)
                                """, (user_id, institution, location))
                                institution_id = cursor.lastrowid
                            
                            # 创建作者-机构关联
                            cursor.execute("""
                                INSERT INTO author_institution (author_id, institution_id)
                                VALUES (%s, %s)
                            """, (author_id, institution_id))
                
                # 处理关键词信息
                keywords = metadata.get('keywords', [])
                if isinstance(keywords, list) and keywords:
                    for keyword in keywords:
                        if not keyword:
                            continue
                        
                        cursor.execute("""
                            SELECT keyword_id FROM keyword
                            WHERE user_id = %s AND keyword_name = %s
                        """, (user_id, keyword))
                        
                        keyword_result = cursor.fetchone()
                        if keyword_result:
                            keyword_id = keyword_result['keyword_id']
                        else:
                            cursor.execute("""
                                INSERT INTO keyword (user_id, keyword_name)
                                VALUES (%s, %s)
                            """, (user_id, keyword))
                            keyword_id = cursor.lastrowid
                        
                        # 创建文档-关键词关联
                        cursor.execute("""
                            INSERT INTO document_keyword (document_id, keyword_id)
                            VALUES (%s, %s)
                        """, (document_id, keyword_id))
                
                conn.commit()
                
                # 记录成功处理的项目
                document_ids.append(document_id)
                file_names.append(file_name)
                
            except Exception as e:
                conn.rollback()
                current_app.logger.error(f"保存元数据失败: {e}")
    
    except Exception as e:
        current_app.logger.error(f"处理元数据列表失败: {e}")
        return jsonify({"error": "服务器错误", "message": f"保存元数据失败: {str(e)}"}), 500
    finally:
        close_db()
    
    if not document_ids:
        return jsonify({
            "code": 1,
            "message": "没有成功保存任何元数据记录",
            "data": { "importedCount": 0 }
        }), 400
    
    return jsonify({
        "code": 0,
        "message": f"成功保存 {len(document_ids)} 条元数据记录",
        "data": {
            "docIds": document_ids,
            "fileNames": file_names,
            "importedCount": len(document_ids)
        }
    })
