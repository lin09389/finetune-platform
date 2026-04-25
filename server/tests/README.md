# Backend Storage Test Commands

Install backend test dependencies in the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
```

Run the database storage tests:

```powershell
.\.venv\Scripts\python.exe -m pytest server\tests\test_storage_phase2.py server\tests\test_storage_phase3.py -q
```

Run only the storage phase 2 baseline:

```powershell
.\.venv\Scripts\python.exe -m pytest server\tests\test_storage_phase2.py -q
```
