Unicode true
!include "MUI2.nsh"

Name "STT Core"
OutFile "dist\STTCore-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\STT Core"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\STTCore\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\STT Core"
  CreateShortCut "$SMPROGRAMS\STT Core\STT Core.lnk" "$INSTDIR\STTCore.exe"
  CreateShortCut "$DESKTOP\STT Core.lnk" "$INSTDIR\STTCore.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STT Core" "DisplayName" "STT Core"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STT Core" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\STT Core.lnk"
  RMDir /r "$SMPROGRAMS\STT Core"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STT Core"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  RMDir /r "$INSTDIR"
SectionEnd
