@echo off
set IDF_PATH=C:\Espressif\frameworks\esp-idf-v5.5.3
set IDF_PYTHON_ENV_PATH=C:\Espressif\python_env\idf5.5_py3.11_env
set PATH=C:\Espressif\python_env\idf5.5_py3.11_env;%PATH%
"C:\Espressif\python_env\idf5.5_py3.11_env\python.exe" "C:\Espressif\frameworks\esp-idf-v5.5.3\tools\export_utils\activate_venv.py"
idf.py -p COM5 build flash monitor
