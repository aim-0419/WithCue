import os

def print_tree(startpath):
    # 무시할 폴더 및 파일 확장자 리스트
    ignore_dirs = {'.git', '__pycache__', 'venv', 'env', '.idea', '.vscode', 'build', 'dist'}
    ignore_exts = {'.bag', '.mp4', '.avi', '.engine', '.pth', '.onnx', '.trt', '.jpg', '.png'}

    for root, dirs, files in os.walk(startpath):
        # 무시할 폴더 제거
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            # 무시할 확장자 및 파일 제거
            if os.path.splitext(f)[1] not in ignore_exts and f != os.path.basename(__file__):
                print(f'{subindent}{f}')

if __name__ == "__main__":
    print("=== Project Structure ===")
    print_tree('.')
    print("=========================")