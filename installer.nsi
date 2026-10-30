Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "FileFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.1.0-beta1.01"
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
!define MUI_WELCOMEPAGE_TEXT "Dictate into your favorite Windows apps with Ctrl + Win.$\r$\n$\r$\nWaveType installs for your account without administrator access. On first launch, the app downloads and verifies Parakeet Redux. Optional Qwen Smart cleanup can be downloaded later in Settings."
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
!define MUI_FINISHPAGE_TEXT "Launch WaveType to download Parakeet Redux. Settings shows model progress and lets you pause, cancel, retry or repair either model. Qwen Smart cleanup is optional.$\r$\n$\r$\nAfter Parakeet is ready, open a text box and hold Ctrl + Win to dictate. Closing the main window leaves WaveType running in the tray."
!define MUI_FINISHPAGE_RUN "$INSTDIR\WaveType.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch WaveType"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION OpenDeveloper
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Visit the developer's GitHub page"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.DataOptionsCreate un.DataOptionsLeave
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Var Dialog
Var StartMenuBox
Var DesktopBox
Var StartupBox
Var StartMenuChoice
Var DesktopChoice
Var StartupChoice
Var DeleteDataBox
Var DeleteDataChoice
Var MaintenanceMutex
Var UiLock
Var EngineLock
Var RemovalFailed

Function .onInit
  SetShellVarContext current
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
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/UPDATE" $1
  ${IfNot} ${Errors}
    IfSilent +3 0
      SetErrorLevel 2
      Abort
    ReadRegStr $1 HKCU "Software\WaveType" "InstallDir"
    ${If} $1 == ""
      SetErrorLevel 2
      Abort
    ${EndIf}
    ${If} $1 != $INSTDIR
      SetErrorLevel 2
      Abort
    ${EndIf}
    IfFileExists "$INSTDIR\WaveType.exe" +3 0
      SetErrorLevel 2
      Abort
    StrCpy $StartMenuChoice ${BST_UNCHECKED}
    StrCpy $DesktopChoice ${BST_UNCHECKED}
    IfFileExists "$SMPROGRAMS\WaveType\WaveType.lnk" 0 +2
      StrCpy $StartMenuChoice ${BST_CHECKED}
    IfFileExists "$DESKTOP\WaveType.lnk" 0 +2
      StrCpy $DesktopChoice ${BST_CHECKED}
  ${EndIf}
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  ${EndIf}
  ${If} $0 != ""
    StrCpy $StartupChoice ${BST_CHECKED}
  ${EndIf}
  StrCpy $UiLock -1
  StrCpy $EngineLock -1
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\WaveTypeMaintenance") p .r0 ?e'
  Pop $1
  StrCpy $MaintenanceMutex $0
  ${If} $1 == 183
    SetErrorLevel 2
    Abort
  ${EndIf}
  InitPluginsDir
  File /oname=$PLUGINSDIR\maintenance.ps1 "packaging\maintenance.ps1"
FunctionEnd

!macro CheckRunningBody
  retry:
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\maintenance.ps1" -Action Check -InstallDir "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    Goto blocked
  ${EndIf}
  CreateDirectory "$LOCALAPPDATA\STTCore"
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\STTCore\ui.lock", i 0xC0000000, i 0, p 0, i 4, i 0, p 0) p.r0'
  StrCpy $UiLock $0
  IntCmp $UiLock -1 blocked
  System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\STTCore\engine.lock", i 0xC0000000, i 0, p 0, i 4, i 0, p 0) p.r0'
  StrCpy $EngineLock $0
  IntCmp $EngineLock -1 blocked
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\maintenance.ps1" -Action Check -InstallDir "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    Return
  ${EndIf}
  blocked:
  System::Call 'kernel32::CloseHandle(p $UiLock)'
  System::Call 'kernel32::CloseHandle(p $EngineLock)'
  StrCpy $UiLock -1
  StrCpy $EngineLock -1
  IfSilent canceled
  MessageBox MB_ICONEXCLAMATION|MB_RETRYCANCEL "WaveType files are in use or unavailable.$\r$\n$\r$\nChoose Exit from the WaveType tray menu and close any WaveType terminal clients. Active recording will stop. If it is unresponsive, end WaveType and its engine in Task Manager.$\r$\n$\r$\nThen choose Retry. Details: $1" IDRETRY retry
  canceled:
  SetErrorLevel 2
  Abort
!macroend
Function CheckRunning
  !insertmacro CheckRunningBody
FunctionEnd
Function un.onInit
  SetRegView 64
  StrCpy $UiLock -1
  StrCpy $EngineLock -1
  StrCpy $DeleteDataChoice ${BST_UNCHECKED}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/REMOVE-DATA" $1
  ${IfNot} ${Errors}
    StrCpy $DeleteDataChoice ${BST_CHECKED}
  ${EndIf}
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\WaveTypeMaintenance") p .r0 ?e'
  Pop $1
  StrCpy $MaintenanceMutex $0
  ${If} $1 == 183
    SetErrorLevel 2
    Abort
  ${EndIf}
  InitPluginsDir
  File /oname=$PLUGINSDIR\maintenance.ps1 "packaging\maintenance.ps1"
FunctionEnd

Function un.CheckRunning
  !insertmacro CheckRunningBody
FunctionEnd

Function un.DataOptionsCreate
  !insertmacro MUI_HEADER_TEXT "Keep your local data?" "Exit WaveType from the tray before continuing. Active recording will stop."
  nsDialogs::Create 1018
  Pop $Dialog
  ${NSD_CreateCheckbox} 0 5u 100% 16u "Also delete all local data"
  Pop $DeleteDataBox
  ${NSD_SetState} $DeleteDataBox $DeleteDataChoice
  ${NSD_CreateLabel} 0 30u 100% 80u "Leave unchecked to keep models, partial downloads, settings, dictionaries, history and logs. Reinstalling restores this data.$\r$\n$\r$\nSelect to remove %LOCALAPPDATA%\STTCore for a fresh installation. Data in custom locations is not removed."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function un.DataOptionsLeave
  ${NSD_GetState} $DeleteDataBox $DeleteDataChoice
FunctionEnd

!macro ReleaseMaintenance
  System::Call 'kernel32::CloseHandle(p $UiLock)'
  System::Call 'kernel32::CloseHandle(p $EngineLock)'
  StrCpy $UiLock -1
  StrCpy $EngineLock -1
  System::Call 'kernel32::CloseHandle(p $MaintenanceMutex)'
  StrCpy $MaintenanceMutex 0
!macroend

Function .onGUIEnd
  !insertmacro ReleaseMaintenance
FunctionEnd
Function un.onGUIEnd
  !insertmacro ReleaseMaintenance
FunctionEnd

Function OptionsCreate
  !insertmacro MUI_HEADER_TEXT "Choose your options" "Shortcuts and startup."
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
  ${NSD_CreateLabel} 0 65u 100% 35u "After installation, WaveType downloads the speech model on first launch. Manage both model downloads in Settings. Qwen Smart cleanup stays optional."
  Pop $0
  ${NSD_CreateLabel} 0 108u 100% 12u "No Python or CUDA Toolkit required. Dictation stays local."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function OptionsLeave
  ${NSD_GetState} $StartMenuBox $StartMenuChoice
  ${NSD_GetState} $DesktopBox $DesktopChoice
  ${NSD_GetState} $StartupBox $StartupChoice
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
  Call CheckRunning
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "dist\WaveType\*.*"
  ${If} ${Errors}
    MessageBox MB_ICONSTOP|MB_OK "Could not copy WaveType. Choose a folder your account can write to, and close any running WaveType instance."
    Abort
  ${EndIf}
  IfFileExists "$INSTDIR\engine\WaveTypeEngine.exe" +3
    MessageBox MB_ICONSTOP|MB_OK "The engine was not copied. Check available disk space and retry setup."
    Abort
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
  ; Windows Settings expects the installed application size in KiB, not installer size.
  ; Downloaded models and personal data live separately and are shown in WaveType.
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "EstimatedSize" $0
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayName" "WaveType"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "Publisher" "ABhattacharya-dev"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "DisplayIcon" '"$INSTDIR\WaveType.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "URLInfoAbout" "https://github.com/ABhattacharya-dev"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType" "NoRepair" 1
  !insertmacro ReleaseMaintenance
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  SetOutPath "$TEMP"
  Call un.CheckRunning
  StrCpy $RemovalFailed 0
  !include "build\uninstall-files.nsh"
  ${If} $RemovalFailed != 0
    DetailPrint "Some application files could not be removed. Uninstall registration was kept."
    IfSilent +2
    MessageBox MB_ICONSTOP|MB_OK "Some WaveType files could not be removed. Close WaveType and retry uninstall. Your uninstall entry and local data have been kept."
    SetErrorLevel 2
    Abort
  ${EndIf}
  System::Call 'kernel32::CloseHandle(p $UiLock)'
  System::Call 'kernel32::CloseHandle(p $EngineLock)'
  StrCpy $UiLock -1
  StrCpy $EngineLock -1
  ${If} $DeleteDataChoice == ${BST_CHECKED}
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\maintenance.ps1" -Action RemoveData'
    Pop $0
    Pop $1
    ${If} $0 != 0
      DetailPrint "Data removal failed: $1"
      IfSilent +2
      MessageBox MB_ICONSTOP|MB_OK "Some local data could not be removed from $LOCALAPPDATA\STTCore. The uninstall entry was kept so you can retry.$\r$\n$1"
      SetErrorLevel 3
      Abort
    ${EndIf}
  ${EndIf}
  Delete "$INSTDIR\Uninstall.exe"
  IfFileExists "$INSTDIR\Uninstall.exe" 0 +4
    DetailPrint "Could not remove Uninstall.exe; registration was kept."
    SetErrorLevel 2
    Abort
  ReadRegStr $0 HKCU "Software\WaveType" "InstallDir"
  ${If} $0 == $INSTDIR
    Delete "$DESKTOP\WaveType.lnk"
    Delete "$SMPROGRAMS\WaveType\WaveType.lnk"
    Delete "$SMPROGRAMS\WaveType\Uninstall WaveType.lnk"
    RMDir "$SMPROGRAMS\WaveType"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WaveType"
    DeleteRegKey HKCU "Software\WaveType"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WaveType"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "STT Core"
  ${EndIf}
  RMDir "$INSTDIR"
  !insertmacro ReleaseMaintenance
SectionEnd
