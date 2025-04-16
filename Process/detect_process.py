import logging
import multiprocessing
import ProcessVideo

def load_process(camera_id, camera_url, q):
    # 부모-자식 파이프 생성
    parent_pipe, child_pipe = multiprocessing.Pipe()

    # 프로세스 생성
    process = multiprocessing.Process(
        target=ProcessVideo,
        args=(camera_url, camera_id, q, child_pipe),
        daemon=True,  # 데몬 프로세스로 설정
    )
    
    return process, parent_pipe
    # ProcessDic[camera_id] = process
    # ppipes[camera_id] = parent_pipe  # 카메라 ID를 키로 부모 파이프 저장