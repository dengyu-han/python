import chromadb
import hashlib
from pypdf import PdfReader
import os

def get_file_md5(file_path: str) ->str:
    hash_md5 = hashlib.md5() 
    with open(file_path, "rb")as f:   #二进制读取
     for chunk in iter(lambda: f.read(4096),b""):    #每一次读取4字节 到空字符停止阅读
        hash_md5.update(chunk)
    return hash_md5.hexdigest()    #以十六进制返回

# 读取txt文件
def get_text(file_path):
    if file_path.endswith(".pdf"):
       full_text= ""
       reader = PdfReader(file_path)
       for page in reader.pages:
          page_text = page.extract_text()
          if page_text:
             full_text += page_text
       return full_text

    elif file_path.endswith(".txt"):    
     with open(file_path, "r", encoding="utf-8") as f:
        full_text = f.read()
     return full_text

def chunk_text(full_text, chunk_size=200, chunk_overlap=30):
    start = 0
    chunks = []
    while start < len(full_text):
        end = start + chunk_size
        chunk = full_text[start:end]
        chunks.append(chunk)
        start = end - chunk_overlap
    return chunks

def changed_one_file(file_path:str, collection):
   file_name = os.path.basename(file_path)
   current_md5 = get_file_md5(file_path)

   res = collection.get(where={"source":file_path})
   old_ids = res["ids"]
   old_metadata_list = res["metadatas"]

   old_md5 = None   #如果曾经入过库，则会等于metadata里对应记录，未入库则为新加入的
   if old_metadata_list:
      old_md5 = old_metadata_list[0]["file_md5"]

   if old_md5 == current_md5:
        print(f"文件{file_path}内容未改变，跳过")
        return

   if len(old_ids) > 0:        #到这是曾经入库 并且内容有改变 还有chunk在向量库集合中，全删除
          print(f"删除集合中对应所有chunk")
          collection.delete(ids=old_ids)

   text = get_text(file_path)
   chunks = chunk_text(text)

   ids = []
   texts = []
   metadatas =[]

   for idx, chunk in enumerate(chunks):
      chunk_id = f"{file_name}-chunk-{idx}"
      ids.append(chunk_id)
      texts.append(chunk)
      metadatas.append({
         "file_md5": current_md5,
         "chunk_index": idx,
         "source":file_path 
      })
         
   collection.add(
      documents=texts,
      ids=ids,
      metadatas=metadatas
   )     
   print(f"{file_path}完成入库，切片数量：{len(chunks)}")

def delete_dirty_data(collection):
    all_result = collection.get()
    all_metadatas = all_result["metadatas"]
    all_ids = all_result["ids"]

     #key:文件路径  value:存文件的切片id
    file_to_id = {}

    for meta, chunk_id in zip(all_metadatas,all_ids):
       if meta is None:
        continue
       source = meta["source"]
       if source not in file_to_id:
          file_to_id[source] = []
       file_to_id[source].append(chunk_id)   

    #然后统一收集源文件已被删除的切片，最后删除
    delete_to_id = []

    for source_path,id_list in file_to_id.items():
       if not os.path.exists(source_path):
        print("该文件已经不存在，删除对应切片")
        delete_to_id.extend(id_list)

    if len(delete_to_id)>0:
     collection.delete(ids=delete_to_id)
     print(f"脏数据已经删除成功")

if __name__ == "__main__":
    # 向量库放在当前代码同级目录 chroma_db
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_or_create_collection(name="jihe")

    delete_dirty_data(collection)
    
    file_list=[
       r"C:\Users\30606\Desktop\操作\colcon.txt",
       r"C:\Users\30606\Desktop\操作\gdb基本命令.txt",
       r"C:\Users\30606\Desktop\操作\Gtest单元测试.txt"
    ]

    for file_path in file_list:
       changed_one_file(file_path, collection)
       print(f"工程结束")