@echo off
setlocal
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
set UIA_CLIENT=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationClient.dll
set UIA_TYPES=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\WPF\UIAutomationTypes.dll
if not exist "%UIA_CLIENT%" set UIA_CLIENT=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\WPF\UIAutomationClient.dll
if not exist "%UIA_TYPES%" set UIA_TYPES=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\WPF\UIAutomationTypes.dll
if not exist "%CSC%" (
  echo csc.exe not found
  exit /b 1
)
"%CSC%" /nologo /target:winexe /platform:anycpu /out:ControlMouseDesktop.exe /reference:System.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll /reference:System.Web.Extensions.dll /reference:System.Windows.Forms.dll /reference:"%UIA_CLIENT%" /reference:"%UIA_TYPES%" Program.cs
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)
echo Build success: ControlMouseDesktop.exe
endlocal
