Unicode true
!include "MUI2.nsh"
!define MUI_ICON "assets\WaveType.ico"
!define MUI_UNICON "assets\WaveType.ico"

Name "WaveType"
OutFile "dist\WaveType-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\WaveType"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\WaveType\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\WaveType"
  CreateShortCut "$SMPROGRAMS\WaveType\WaveType.lnk" "$INSTDIR\WaveType.exe"
  CreateShortCut "$DESKTOP\WaveType.lnk" "$INSTDIR\WaveType.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayName" "WaveType"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\WaveType.lnk"
  RMDir /r "$SMPROGRAMS\WaveType"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  RMDir /r "$INSTDIR"
SectionEnd
