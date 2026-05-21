#### 获取知识库列表
curl --request GET \
  --url 'https://api.dify.ai/v1/datasets?page=1&limit=20' \
  --header 'Authorization: Bearer YOUR_DATASET_API_KEY'

  {
  "data": [
    {
      "id": "c42e2a6e-40b3-4330-96f8-f1e4d768e8c9",
      "name": "Product Documentation",
      "description": "产品API 技术文档",
      "provider": "vendor",
      "permission": "only_me",
      "data_source_type": null,
      "indexing_technique": "high_quality",
      "app_count": 0,
      "document_count": 12,
      "word_count": 15300,
      "created_by": "ad313dd6-ef04-4dd1-a5b0-c0f0b9e2e7e4",
      "author_name": "admin",
      "created_at": 1741267200,
      "updated_by": "ad313dd6-ef04-4dd1-a5b0-c0f0b9e2e7e4",
      "updated_at": 1741267200,
      "embedding_model": "text-embedding-3-small",
      "embedding_model_provider": "openai",
      "embedding_available": true,
      "tags": [],
      "total_documents": 12,
      "total_available_documents": 12,
      "enable_api": true
    }
  ],
  "has_more": false,
  "limit": 20,
  "total": 1,
  "page": 1
}

#### 获取知识库内文档列表
curl --request GET \
  --url 'https://api.dify.ai/v1/datasets/c42e2a6e-40b3-4330-96f8-f1e4d768e8c9/documents?page=1&limit=20' \
  --header 'Authorization: Bearer YOUR_DATASET_API_KEY'

  {
  "data": [
    {
      "id": "a8e0e5b5-78c6-4130-a5ce-25feb0e0b4ac",
      "position": 1,
      "data_source_type": "upload_file",
      "data_source_info": {
        "upload_file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
      },
      "data_source_detail_dict": {
        "upload_file": {
          "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "name": "guide.txt",
          "size": 2048,
          "extension": "txt",
          "mime_type": "text/plain",
          "created_by": "ad313dd6-ef04-4dd1-a5b0-c0f0b9e2e7e4",
          "created_at": 1741267200
        }
      },
      "dataset_process_rule_id": "e1f2a3b4-c5d6-7890-ef12-345678901234",
      "name": "guide.txt",
      "created_from": "api",
      "created_by": "ad313dd6-ef04-4dd1-a5b0-c0f0b9e2e7e4",
      "created_at": 1741267200,
      "tokens": 512,
      "indexing_status": "completed",
      "error": null,
      "enabled": true,
      "disabled_at": null,
      "disabled_by": null,
      "archived": false,
      "display_status": "available",
      "word_count": 350,
      "hit_count": 0,
      "doc_form": "text_model",
      "doc_metadata": [],
      "summary_index_status": null,
      "need_summary": false
    }
  ],
  "has_more": false,
  "limit": 20,
  "total": 1,
  "page": 1
}