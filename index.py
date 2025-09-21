import torch
print(torch.cuda.is_available())  # should be True
print(torch.cuda.get_device_name(0))  # should show RTX 3050


import whisper

model = whisper.load_model("medium").to("cuda")  # forces GPU usage
audio_path = r"uploads\uZ8Ayp6299IuPvszAAAH_temp.wav"
result = model.transcribe(audio_path)
print(result["text"])
