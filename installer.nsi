Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.1.0-beta.1"
!endif
!ifndef FILE_VERSION
  !define FILE_VERSION "0.1.0.0"
!endif

Name "WaveType"
OutFile "dist\WaveType-${APP_VERSION}-Setup-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\WaveType"
InstallDirRegKey HKCU "Software\WaveType" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
BrandingText "WaveType | Local dictation"
VIProductVersion "${FILE_VERSION}"
VIAddVersionKey "ProductName" "WaveType"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "WaveType Windows x64 Setup"
VIAddVersionKey "LegalCopyright" "WaveType contributors"

!define MUI_ICON "assets\WaveType.ico"
!define MUI_UNICON "assets\WaveType.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "assets\installer\header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "assets\installer\wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "assets\installer\wizard.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to WaveType"
!define MUI_WELCOMEPAGE_TEXT "Dictate into your favorite Windows apps with Ctrl + Win.$\r$\n$\r$\nSpeech recognition and optional Smart cleanup run on this computer. Setup downloads and verifies the speech model and runtime; an internet connection and several GB of free space are needed.$\r$\n$\r$\nWaveType installs for your account without administrator access."
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_HEADER_TEXT "Privacy and license notices"
!define MUI_PAGE_HEADER_SUBTEXT "Review local data handling and bundled components."
!define MUI_LICENSEPAGE_TEXT_TOP "WaveType keeps speech processing local. Review privacy and license notices."
!define MUI_LICENSEPAGE_BUTTON "Next >"
!insertmacro MUI_PAGE_LICENSE "packaging\INSTALL-NOTICES.txt"
Page custom OptionsCreate OptionsLeave
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE VerifyDirectory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "WaveType is installed"
!define MUI_FINISHPAGE_TEXT "Open a text box, then hold Ctrl + Win to dictate or tap to lock recording.$\r$\n$\r$\nClosing the main window leaves WaveType running in the tray. Choose Exit from the tray to stop it.$\r$\n$\r$\nIf a model download was interrupted, launch WaveType with an internet connection to resume it."
!define MUI_FINISHPAGE_RUN "$INSTDIR\WaveType.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch WaveType"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION OpenDeveloper
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Visit the developer's GitHub page"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Var Dialog
Var StartMenuBox
Var DesktopBox
Var StartupBox
Var CleanupBox
Var StartMenuChoice
Var DesktopChoice
Var StartupChoice
Var CleanupChoice

Function .onInit
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_ICONSTOP|MB_OK "This release requires an Intel/AMD x64 Windows 10 or 11 PC."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP|MB_OK "WaveType requires Windows 10 or later."
    Abort
  ${EndIf}
  SetRegView 64
  StrCpy $StartMenuChoice ${BST_CHECKED}
  StrCpy $DesktopChoice ${BST_CHECKED}
  StrCpy $StartupChoice ${BST_UNCHECKED}
  StrCpy $CleanupChoice ${BST_UNCHECKED}
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  ${EndIf}
  ${If} $0 != ""
    StrCpy $StartupChoice ${BST_CHECKED}
  ${EndIf}
  Call CheckRunning
FunctionEnd

!macro CheckRunningBody
  IfFileExists "$LOCALAPPDATA\STTCore\ui.lock" 0 done
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\STTCore\ui.lock", i 0, i 0, p 0, i 3, i 0, p 0) p.r0'
  ${If} $0 == -1
    System::Call 'kernel32::GetLastError() i.r1'
    ${If} $1 == 32
      MessageBox MB_ICONEXCLAMATION|MB_OK "Please choose Exit from the WaveType tray menu, then run setup again."
      Abort
    ${EndIf}
  ${Else}
    System::Call 'kernel32::CloseHandle(p r0)'
  ${EndIf}
  done:
!macroend
Function CheckRunning
  !insertmacro CheckRunningBody
FunctionEnd
Function un.onInit
  SetRegView 64
  !insertmacro CheckRunningBody
FunctionEnd

Function OptionsCreate
  !insertmacro MUI_HEADER_TEXT "Choose your options" "Shortcuts, startup and optional Smart cleanup."
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}
  ${NSD_CreateCheckbox} 0 0u 100% 14u "Create a Start Menu shortcut"
  Pop $StartMenuBox
  ${NSD_SetState} $StartMenuBox $StartMenuChoice
  ${NSD_CreateCheckbox} 0 20u 100% 14u "Create a desktop shortcut"
  Pop $DesktopBox
  ${NSD_SetState} $DesktopBox $DesktopChoice
  ${NSD_CreateCheckbox} 0 40u 100% 14u "Start WaveType when I sign in to Windows"
  Pop $StartupBox
  ${NSD_SetState} $StartupBox $StartupChoice
  ${NSD_CreateCheckbox} 0 60u 100% 14u "Download the optional Smart cleanup model now"
  Pop $CleanupBox
  ${NSD_SetState} $CleanupBox $CleanupChoice
  ${NSD_CreateLabel} 12u 80u 94% 30u "Smart cleanup fixes grammar and spoken corrections locally. It needs an additional download and several GB of RAM. You can download and enable it later in Settings."
  Pop $0
  ${NSD_CreateLabel} 0 116u 100% 12u "No Python or CUDA Toolkit required. Dictation stays local."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function OptionsLeave
  ${NSD_GetState} $StartMenuBox $StartMenuChoice
  ${NSD_GetState} $DesktopBox $DesktopChoice
  ${NSD_GetState} $StartupBox $StartupChoice
  ${NSD_GetState} $CleanupBox $CleanupChoice
FunctionEnd

Function VerifyDirectory
  IfFileExists "$INSTDIR\WaveType.exe" done
  FindFirst $0 $1 "$INSTDIR\*"
  IfErrors done
  loop:
    ${If} $1 != "."
    ${AndIf} $1 != ".."
    ${AndIf} $1 != ""
      FindClose $0
      MessageBox MB_ICONEXCLAMATION|MB_OK "Choose an empty folder or an existing WaveType installation folder."
      Abort
    ${EndIf}
    FindNext $0 $1
    IfErrors empty
    Goto loop
  empty:
    FindClose $0
  done:
FunctionEnd

Function OpenDeveloper
  ExecShell "open" "https://github.com/ABhattacharya-dev"
FunctionEnd

Section "WaveType" MainSection
  SetShellVarContext current
  SetRegView 64
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "dist\WaveType\*.*"
  ${If} ${Errors}
    MessageBox MB_ICONSTOP|MB_OK "Could not copy WaveType. Choose a folder your account can write to, and close any running WaveType instance."
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ${If} $StartMenuChoice == ${BST_CHECKED}
    CreateDirectory "$SMPROGRAMS\WaveType"
    CreateShortCut "$SMPROGRAMS\WaveType\WaveType.lnk" "$INSTDIR\WaveType.exe"
    CreateShortCut "$SMPROGRAMS\WaveType\Uninstall WaveType.lnk" "$INSTDIR\Uninstall.exe"
  ${Else}
    Delete "$SMPROGRAMS\WaveType\WaveType.lnk"
    Delete "$SMPROGRAMS\WaveType\Uninstall WaveType.lnk"
    RMDir "$SMPROGRAMS\WaveType"
  ${EndIf}
  ${If} $DesktopChoice == ${BST_CHECKED}
    CreateShortCut "$DESKTOP\WaveType.lnk" "$INSTDIR\WaveType.exe"
  ${Else}
    Delete "$DESKTOP\WaveType.lnk"
  ${EndIf}
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  ${If} $StartupChoice == ${BST_CHECKED}
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType" '"$INSTDIR\WaveType.exe"'
  ${Else}
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType"
  ${EndIf}
  WriteRegStr HKCU "Software\WaveType" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayName" "WaveType"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "Publisher" "ABhattacharya-dev"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayIcon" '"$INSTDIR\WaveType.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "URLInfoAbout" "https://github.com/ABhattacharya-dev"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "NoRepair" 1

  DetailPrint "Preparing verified local speech files. Internet is needed for missing files."
  ${If} $CleanupChoice == ${BST_CHECKED}
    nsExec::ExecToLog '"$INSTDIR\engine\WaveTypeEngine.exe" setup --cleanup'
  ${Else}
    nsExec::ExecToLog '"$INSTDIR\engine\WaveTypeEngine.exe" setup'
  ${EndIf}
  Pop $0
  ${If} $0 != 0
    DetailPrint "Model setup did not finish. The app is installed; launch it to resume downloads."
    IfSilent download_done
    MessageBox MB_ICONEXCLAMATION|MB_OK "WaveType is installed, but model setup could not finish. Launch WaveType with an internet connection to resume. Smart cleanup remains optional."
  ${EndIf}
  download_done:
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  Delete "$DESKTOP\WaveType.lnk"
  Delete "$SMPROGRAMS\WaveType\WaveType.lnk"
  Delete "$SMPROGRAMS\WaveType\Uninstall WaveType.lnk"
  RMDir "$SMPROGRAMS\WaveType"
  ReadRegStr $0 HKCU "Software\WaveType" "InstallDir"
  ${If} $0 == $INSTDIR
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType"
    DeleteRegKey HKCU "Software\WaveType"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  ${EndIf}
  !include "build\uninstall-files.nsh"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
