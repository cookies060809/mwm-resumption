@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
echo Running C independent pipeline: tests, experiments, reproducibility, demo, bundle.
python run_full_check.py
set "MWM_CHECK_EXIT=%errorlevel%"
if not "%MWM_CHECK_EXIT%"=="0" echo Check failed. See results\verification\verification.json and logs.
if "%MWM_CHECK_EXIT%"=="0" echo Done. Open results\full_run\demo.html or results\full_run\report.md.
if not "%MWM_NO_PAUSE%"=="1" pause
exit /b %MWM_CHECK_EXIT%
