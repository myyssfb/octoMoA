; octoMoA - Windows Installer (NSIS 3.x)

; -- 基本定义 --
!define PRODUCT_NAME "octoMoA"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "octoMoA"
!define PRODUCT_WEB_SITE "https://github.com/octomoa"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\octoMoA.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

SetCompressor lzma
ManifestDPIAware true

; -- 现代 UI --
!include "MUI2.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "app\icon.ico"
!define MUI_UNICON "app\icon.ico"

; 欢迎页
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${PRODUCT_NAME}"
!define MUI_WELCOMEPAGE_TEXT "本向导将引导您完成 ${PRODUCT_NAME} ${PRODUCT_VERSION} 的安装。$\r$\n$\r$\n${PRODUCT_NAME} 是一个本地多模型聚合代理，通过 Mixture of Agents 技术，让您的编程工具可以透明地使用多个 AI 模型协作回答。"

; 许可协议
!define MUI_LICENSEPAGE_BUTTON "我同意(&I)"
!define MUI_LICENSEPAGE_TEXT_TOP "请阅读以下许可协议："

; 完成页
!define MUI_FINISHPAGE_RUN "$INSTDIR\octoMoA.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ${PRODUCT_NAME}"

; -- 安装页面 --
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; -- 卸载页面 --
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"

; -- 安装器属性 --
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "octoMoA-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\octoMoA"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show
BrandingText "${PRODUCT_PUBLISHER}"

; --- Install ---

Section "!octoMoA (必需)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; 复制所有程序文件
  File /r "dist\octoMoA\*.*"

  ; 数据目录（用户配置和日志）
  CreateDirectory "$INSTDIR\data"

  ; -- 写入注册表 --
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\octoMoA.exe"
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "Path" "$INSTDIR"

  ; 卸载信息（控制面板可见）
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\octoMoA.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"

  ; 写入卸载程序
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; -- 开始菜单 --
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\octoMoA.exe"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 octoMoA.lnk" "$INSTDIR\uninstall.exe"

  ; -- 桌面快捷方式 --
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\octoMoA.exe"

SectionEnd

Section "开机自启" SecAutoStart
  ; 注册表 Run 键
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\octoMoA.exe"
SectionEnd

SectionGroup /e "API 提供商预设" SecProviders

  Section "DeepSeek" SecDS
    ; 预设标记文件，首次启动时自动导入
    SetOutPath "$INSTDIR\data"
    FileOpen $0 "$INSTDIR\data\preset_deepseek" w
    FileClose $0
  SectionEnd

  Section "Mimo" SecMimo
    SetOutPath "$INSTDIR\data"
    FileOpen $0 "$INSTDIR\data\preset_mimo" w
    FileClose $0
  SectionEnd

SectionGroupEnd

; -- 描述信息（鼠标悬停时显示）--
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "octoMoA 核心程序，包含多模型聚合代理和管理面板。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutoStart} "开机时自动启动 octoMoA 到系统托盘。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDS} "预置 DeepSeek 模型端点（需自行配置 API Key）。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMimo} "预置 Mimo 模型端点（需自行配置 API Key）。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; --- Uninstall ---

Section "Uninstall"
  ; 杀掉运行中的进程
  nsExec::Exec "taskkill /F /IM octoMoA.exe"
  Sleep 1000

  ; 删除快捷方式
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 octoMoA.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; 删除开机自启
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"

  ; 删除程序文件
  RMDir /r "$INSTDIR"

  ; 删除注册表
  DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

  ; 询问是否删除用户数据
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除所有用户配置和数据？$\r$\n$\r$\n(包括 API Key 配置、历史记录等)" IDYES delete_data IDNO skip_data
  delete_data:
    RMDir /r "$APPDATA\octoMoA"
  skip_data:
SectionEnd
