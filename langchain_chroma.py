from langchain_community.document_loaders import  TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
import hashlib
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma

def get_file_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def changed_one_file(file_path: str, vector_db: Chroma):
    # 拿到底层原生chromadb collection
    collection = vector_db._collection

    current_md5 = get_file_md5(file_path)
    file_name = os.path.basename(file_path)

    res = collection.get(where={"source": file_path})
    old_ids = res["ids"]
    old_meta_list = res["metadatas"]

    old_md5 = None
    if old_meta_list:
        old_md5 = old_meta_list[0]["file_md5"]

    if old_md5 == current_md5:
        print(f"文件{file_name}内容未改变，跳过")
        return

    if len(old_ids) > 0:
        print("文件内容有改变，删除对应切片")
        collection.delete(ids=old_ids)

    loader = TextLoader(
        file_path,
        encoding="UTF-8"
    )
    docs = loader.load()
    print(f"总共加载文档片段数量：{len(docs)}")
    for idx, doc in enumerate(docs):
        print(f"\n==== 第{idx+1}个文件 ====")
        print(f"source路径：{doc.metadata['source']}")
        print(f"文本前100字符：{doc.page_content[:100]}")

    content_split = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=20,
        length_function=len,
    )
    split_docs_chunks = content_split.split_documents(docs)
    print(f"所有文件内容切片长度:{len(split_docs_chunks)}")

    for chunk_idx, chunk_doc in enumerate(split_docs_chunks):
        chunk_doc.metadata["file_md5"] = current_md5
        chunk_doc.metadata["chunk_index"] = chunk_idx
        chunk_doc.metadata["source"] = file_path

    # add_documents 添加分片
    vector_db.add_documents(split_docs_chunks)
    print("切片入库完成")


def delete_dirty_data(vector_db: Chroma):
    collection = vector_db._collection
    all_result = collection.get()
    all_metadatas = all_result["metadatas"]
    all_ids = all_result["ids"]

    file_to_id = {}
    for meta, chunk_id in zip(all_metadatas, all_ids):
        if meta is None:
            continue
        source = meta["source"]
        if source not in file_to_id:
            file_to_id[source] = []
        file_to_id[source].append(chunk_id)

    delete_to_id = []
    for source_path, id_list in file_to_id.items():
        if not os.path.exists(source_path):
            print("原文件已经被删除，清理脏分片")
            delete_to_id.extend(id_list)
    if len(delete_to_id) > 0:
        collection.delete(ids=delete_to_id)
        print(f"脏分片清理完成")


if __name__ == "__main__":
    embedding = FastEmbedEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
    vector_db = Chroma(
        collection_name="jihe",
        embedding_function=embedding,
        persist_directory="./langchain_chroma_db"
    )

    delete_dirty_data(vector_db)

    file_list = [
        r"C:\Users\30606\Desktop\操作\colcon.txt",
        r"C:\Users\30606\Desktop\操作\gdb基本命令.txt",
        r"C:\Users\30606\Desktop\操作\Gtest单元测试.txt",
        r"C:\Users\30606\Desktop\医学文档-高血压.txt"
    ]

    for file_path in file_list:
        changed_one_file(file_path, vector_db)
    print("工程结束")
