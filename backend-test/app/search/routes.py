from flask import request, jsonify, current_app, g, make_response
from . import search_bp
from app.db import query_db
from app.utils.decorators import login_required
import jwt

@search_bp.route('/', methods=['GET'])
def search_library():
    """搜索库中的文档、作者和机构"""
    # 支持从URL参数获取token
    token = request.args.get('token')
    
    # 如果提供了token，尝试解码获取用户ID
    user_id = None
    if token:
        try:
            payload = jwt.decode(
                token, 
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config.get('JWT_ALGORITHM', 'HS256')]
            )
            user_id = payload.get('user_id')
        except jwt.PyJWTError as e:
            current_app.logger.error(f"Token解析失败: {e}")
            return jsonify({
                "error": "认证失败", 
                "message": "无效的认证令牌"
            }), 401
    
    # 如果无法获取用户ID
    if not user_id:
        return jsonify({
            "error": "认证失败", 
            "message": "请提供有效的认证信息"
        }), 401
    
    query = request.args.get('q', '')
    
    if not query or len(query) < 2:
        return jsonify({
            "code": 1,
            "message": "搜索词太短",
            "data": {"results": []}
        }), 400
    
    search_term = f"%{query}%"
    results = []
    
    try:
        # 搜索文档标题和DOI (最多4个结果)
        documents = query_db("""
            SELECT document_id as id, title as name, 'document' as type, 
                   CASE 
                       WHEN doi = %s THEN 'doi'
                       WHEN doi LIKE %s THEN 'doi'
                       ELSE 'title'
                   END as matchField,
                   dir.directory_name as folderName, dir.directory_id as folderId,
                   doi
            FROM document d
            JOIN directory dir ON d.directory_id = dir.directory_id
            WHERE d.user_id = %s AND (d.title LIKE %s OR d.doi LIKE %s OR d.doi = %s)
            ORDER BY CASE 
                WHEN d.doi = %s THEN 0           -- DOI精确匹配优先级最高
                WHEN d.title = %s THEN 1          -- 标题精确匹配次之
                WHEN d.title LIKE %s THEN 2       -- 标题开头匹配
                WHEN d.doi LIKE %s THEN 3         -- DOI部分匹配
                ELSE 4                            -- 标题包含匹配
            END
            LIMIT 10
        """, (query, search_term, user_id, search_term, search_term, query, query, query, f"{query}%", search_term))
        
        # 构建文档路径
        for doc in documents:
            doc['path'] = f"文件夹: {doc['folderName']}"
            if doc['matchField'] == 'doi' and doc.get('doi'):
                doc['matchDetail'] = f"DOI: {doc['doi']}"
            results.append(doc)
        
        # 搜索作者名称 (最多3个结果)
        authors = query_db("""
            SELECT DISTINCT a.author_id as id, a.author_name as name, 'author' as type, 'author' as matchField
            FROM author a
            WHERE a.user_id = %s AND a.author_name LIKE %s
            LIMIT 3
        """, (user_id, search_term))
        
        results.extend(authors)
        
        # 搜索机构名称 (最多3个结果)
        institutions = query_db("""
            SELECT DISTINCT i.institution_id as id, i.institution_name as name, 'institution' as type, 
                   'affiliation' as matchField, i.institution_location as location
            FROM institution i
            WHERE i.user_id = %s AND i.institution_name LIKE %s
            LIMIT 3
        """, (user_id, search_term))
        
        for inst in institutions:
            if inst.get('location'):
                inst['path'] = inst['location']
            results.append(inst)
        
        return jsonify({
            "code": 0,
            "message": "搜索成功",
            "data": {
                "query": query,
                "results": results
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"搜索失败: {e}")
        return jsonify({
            "error": "服务器错误", 
            "message": f"搜索失败: {str(e)}"
        }), 500
