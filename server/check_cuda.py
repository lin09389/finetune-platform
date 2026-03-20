"""检查CUDA可用性"""
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'Device: {torch.cuda.get_device_name(0)}')
    print(f'Device count: {torch.cuda.device_count()}')
else:
    print('Device: CPU')
