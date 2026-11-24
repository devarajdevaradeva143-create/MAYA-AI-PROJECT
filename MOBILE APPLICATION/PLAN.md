# MAYA AI — Mobile App Full Plan (Android)

> Ithu Android app-oda **full build plan**.
> Vera AI coder ithai paathu phase-by-phase code pannalam.
> Simple Thanglish-la ezhuthirukken — puriya easy-ah.

**Status:** Phases 0-12 implemented (Phase 9 native build + JNI wired; model file + chat fallback optional). Debug + Release APK build & install.
**App name:** Maya AI
**Package:** `com.devaraj.maya`
**Project folder:** `C:\Users\devar\Desktop\MAYA AI PROJECT\MOBILE APP\`

---

## 0. Vera AI coder-ku — first ithai padikkavum

1. `AGENTS.md` (project root) — hard rules.
2. `docs\API-CONTRACT.md` — laptop server API. **Idhu single source of truth.**
3. Ithu file — app design.
4. `MAYA AI\config\settings.yaml` — privacy / permission defaults.

**Build order:** Phase 0 → 12. Phase skip panna koodadhu.
Every phase-kku **Definition of Done (DoD)** irukku — adhu pass aanaa mattum next phase.
Phase 3 (pairing) + Phase 4 (chat) mudiyum pothu laptop server (Windows plan Phase 9) ready-a irukkanum. Illa-na `MockWebServer` fixture use pannu.

**Hard rules (repeat):**
- `JARVIS\OpenJarvis\` — **READ ONLY** ❌ (mobile repo-la thoda vendam)
- Ellam code `MOBILE APP\` la mattum ✅
- Cloud / Gemini / analytics / ads **illa** ❌
- Personal data phone-la mattum 🔒
- Important action → user permission ⚠️
- English UI (strings.xml), Thanglish chat okay ✅

---

## 1. App enna?

Maya AI mobile app — Android phone-la run aagum personal assistant.

Three jobs:

1. **Laptop remote** — WiFi / USB / Bluetooth-la laptop Maya AI-ah use pannum (full Qwen 3B power).
2. **Phone AI** — laptop illa-na phone-la tamil-lm-2b 2B (offline fallback).
3. **Phone + laptop control** — chat command moolam apps, files, messages, system.

Maya = **command only**. Thana ethuvum pannadhu ❌.

---

## 2. Confirmed decisions

| Item | Decision |
|---|---|
| Platform | Android only |
| Min SDK | **36 (Android 16)** |
| Target / compile SDK | 36 |
| Language | Kotlin (native) |
| UI | Jetpack Compose + Material 3 |
| App UI language | English |
| Themes | Dark + Light + System |
| Phone model | tamil-lm-2b Instruct (Q4_K_M GGUF) |
| Laptop model | Qwen 3B |
| Connection | WiFi + Bluetooth + USB |
| Internet remote | **Ippo venam** ❌ |
| Pairing | PIN + QR secure; auto-connect optional (user choice) |
| Phone control | Full — apps, notifications, SMS, calls, files, screen |
| Voice | Android STT + Android TTS + Piper |
| Screens | Full app (Chat, Voice, Laptop, Phone, Monitoring, Settings) |
| Architecture | MVVM + Repository, manual DI |
| Server | Laptop FastAPI (`docs\API-CONTRACT.md`) |

---

## 3. Environment (verified 2026-11-17)

| Tool | Status |
|---|---|
| Java | ✅ OpenJDK 21.0.13 (Temurin) |
| Android SDK | ✅ `%LOCALAPPDATA%\Android\Sdk` |
| Platforms | ✅ android-35, android-36 |
| Build tools | ✅ 34.0.0, 35.0.0, 36.0.0 |
| ADB | ✅ `platform-tools\adb.exe` |
| Gradle | ❌ global illa → **wrapper** use pannu |
| Android Studio | ❌ illa → CLI build |
| Emulator | ⚠️ verify pannanum (system image install pannala) |

**Rule:** Machine-la irukkura SDK-ah use pannu; Android Studio install panna avasiyam illa.

---

## 4. Architecture

```
┌────────────────────────────────────────────┐
│                ANDROID APP                 │
│                                            │
│  Compose UI (6 screens)                    │
│      │                                     │
│  ViewModel (StateFlow)                     │
│      │                                     │
│  Repository layer                          │
│   ├─ ChatRepository ──► ChatSocket (WS)    │
│   ├─ PairingRepository ──► MayaApi (REST)  │
│   ├─ ConnectionRepository                  │
│   ├─ MonitorRepository                     │
│   ├─ LaptopControlRepository               │
│   └─ PhoneControlRepository                │
│      │                                     │
│  Data: Room + DataStore + Keystore         │
│                                            │
│  Local AI: llama.cpp JNI (tamil-lm-2b 2B)  │
│  Voice: SpeechRecognizer + Android TTS     │
│         + Piper (sherpa-onnx)              │
│  Service: foreground mic / wake            │
└───────────────┬────────────────────────────┘
                │ WiFi LAN / USB (adb reverse) / BT PAN
        ┌───────▼─────────┐
        │  LAPTOP SERVER  │
        │  FastAPI :8420  │
        │  Qwen 3B        │
        │  Windows/Fedora │
        └─────────────────┘
```

**Source-of-truth priority for chat:**
1. Laptop connected → laptop model (WS streaming)
2. Illa-na → phone model (on-device)
3. Rendum illa-na → error card + setup hint

---

## 5. Tech stack — exact versions

> Versions pin pannirukken. Build fail aanaa (Maven-la illa-na) next patch version try pannu — API break irukkadhu.

| Layer | Library | Version |
|---|---|---|
| Build | AGP | 8.10.1 |
| Build | Gradle wrapper | 8.11.1 |
| Language | Kotlin | 2.1.21 |
| Compose compiler | Kotlin compose plugin | 2.1.21 |
| KSP | `com.google.devtools.ksp` | 2.1.21-2.0.1 |
| Compose BOM | `androidx.compose:compose-bom` | 2025.05.01 |
| Core | `androidx.core:core-ktx` | 1.16.0 |
| Lifecycle | `androidx.lifecycle:*` | 2.9.0 |
| Activity | `androidx.activity:activity-compose` | 1.10.1 |
| Navigation | `androidx.navigation:navigation-compose` | 2.9.0 |
| Room | `androidx.room:*` | 2.7.1 |
| DataStore | `androidx.datastore:datastore-preferences` | 1.1.7 |
| OkHttp | `com.squareup.okhttp3:okhttp` | 4.12.0 |
| Retrofit | `com.squareup.retrofit2:retrofit` | 2.11.0 |
| Serialization | `org.jetbrains.kotlinx:kotlinx-serialization-json` | 1.8.1 |
| Coroutines | `org.jetbrains.kotlinx:kotlinx-coroutines-android` | 1.10.2 |
| QR scan | `com.journeyapps:zxing-android-embedded` | 4.3.0 |
| Images | `io.coil-kt:coil-compose` | 2.7.0 |
| Unit test | JUnit | 4.13.2 |
| Android test | `androidx.test.ext:junit` | 1.2.1 |
| UI test | Espresso | 3.6.1 |
| Mock server | `com.squareup.okhttp3:mockwebserver` | 4.12.0 |
| Native AI | llama.cpp (source / JNI) | pin at build time |
| NDK | `27.2.12479018` | Phase 9 |
| CMake | `3.22.1` | Phase 9 |
| Piper | sherpa-onnx Android AAR | pin at build time |

**Native library version rule:** llama.cpp / sherpa-onnx exact version-ah build sariyana pothu `gradle/libs.versions.toml`-la pin pannu. Guess pannaadhu — release page verify pannu.

---

## 6. Project setup — exact Gradle files

### 6.1 Folder create

```
MOBILE APP\
├─ PLAN.md
├─ README.md
├─ settings.gradle.kts
├─ build.gradle.kts
├─ gradle.properties
├─ local.properties          ← git-ignored
├─ keystore.properties       ← git-ignored (release only)
├─ .gitignore
├─ gradlew / gradlew.bat
├─ gradle\
│  ├─ libs.versions.toml
│  └─ wrapper\
│     ├─ gradle-wrapper.jar
│     └─ gradle-wrapper.properties
└─ app\
   ├─ build.gradle.kts
   ├─ proguard-rules.pro
   └─ src\
      ├─ main\
      ├─ test\
      └─ androidTest\
```

### 6.2 `settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "MayaAI"
include(":app")
```

### 6.3 `gradle/libs.versions.toml`

```toml
[versions]
agp = "8.10.1"
kotlin = "2.1.21"
ksp = "2.1.21-2.0.1"
composeBom = "2025.05.01"
coreKtx = "1.16.0"
lifecycle = "2.9.0"
activityCompose = "1.10.1"
navigation = "2.9.0"
room = "2.7.1"
datastore = "1.1.7"
okhttp = "4.12.0"
retrofit = "2.11.0"
serialization = "1.8.1"
coroutines = "1.10.2"
zxing = "4.3.0"
coil = "2.7.0"
junit = "4.13.2"
androidxJunit = "1.2.1"
espresso = "3.6.1"

[libraries]
androidx-core-ktx = { module = "androidx.core:core-ktx", version.ref = "coreKtx" }
androidx-lifecycle-runtime = { module = "androidx.lifecycle:lifecycle-runtime-ktx", version.ref = "lifecycle" }
androidx-lifecycle-viewmodel-compose = { module = "androidx.lifecycle:lifecycle-viewmodel-compose", version.ref = "lifecycle" }
androidx-lifecycle-runtime-compose = { module = "androidx.lifecycle:lifecycle-runtime-compose", version.ref = "lifecycle" }
androidx-activity-compose = { module = "androidx.activity:activity-compose", version.ref = "activityCompose" }
androidx-navigation-compose = { module = "androidx.navigation:navigation-compose", version.ref = "navigation" }

compose-bom = { module = "androidx.compose:compose-bom", version.ref = "composeBom" }
compose-ui = { module = "androidx.compose.ui:ui" }
compose-ui-graphics = { module = "androidx.compose.ui:ui-graphics" }
compose-ui-tooling = { module = "androidx.compose.ui:ui-tooling" }
compose-ui-tooling-preview = { module = "androidx.compose.ui:ui-tooling-preview" }
compose-material3 = { module = "androidx.compose.material3:material3" }
compose-material-icons = { module = "androidx.compose.material:material-icons-extended" }
compose-ui-test-junit4 = { module = "androidx.compose.ui:ui-test-junit4" }
compose-ui-test-manifest = { module = "androidx.compose.ui:ui-test-manifest" }

room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
room-ktx = { module = "androidx.room:room-ktx", version.ref = "room" }
room-compiler = { module = "androidx.room:room-compiler", version.ref = "room" }

datastore-preferences = { module = "androidx.datastore:datastore-preferences", version.ref = "datastore" }

okhttp = { module = "com.squareup.okhttp3:okhttp", version.ref = "okhttp" }
okhttp-logging = { module = "com.squareup.okhttp3:logging-interceptor", version.ref = "okhttp" }
mockwebserver = { module = "com.squareup.okhttp3:mockwebserver", version.ref = "okhttp" }
retrofit = { module = "com.squareup.retrofit2:retrofit", version.ref = "retrofit" }
retrofit-serialization = { module = "com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter", version = "1.0.0" }
kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "serialization" }
kotlinx-coroutines-android = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-android", version.ref = "coroutines" }
kotlinx-coroutines-test = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-test", version.ref = "coroutines" }

zxing-embedded = { module = "com.journeyapps:zxing-android-embedded", version.ref = "zxing" }
coil-compose = { module = "io.coil-kt:coil-compose", version.ref = "coil" }

junit = { module = "junit:junit", version.ref = "junit" }
androidx-junit = { module = "androidx.test.ext:junit", version.ref = "androidxJunit" }
espresso-core = { module = "androidx.test.espresso:espresso-core", version.ref = "espresso" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
kotlin-compose = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
kotlin-serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
```

### 6.4 Root `build.gradle.kts`

```kotlin
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
}
```

### 6.5 `app/build.gradle.kts`

```kotlin
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

val keystoreFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystoreFile.exists()) keystoreFile.inputStream().use { load(it) }
}

android {
    namespace = "com.devaraj.maya"
    compileSdk = 36
    // ndkVersion = "27.2.12479018"  // Phase 9-la mattum uncomment pannu

    defaultConfig {
        applicationId = "com.devaraj.maya"
        minSdk = 36
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true
    }

    signingConfigs {
        if (keystoreProps.isNotEmpty()) {
            create("release") {
                storeFile = file(keystoreProps["storeFile"] as String)
                storePassword = keystoreProps["storePassword"] as String
                keyAlias = keystoreProps["keyAlias"] as String
                keyPassword = keystoreProps["keyPassword"] as String
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    implementation(libs.datastore.preferences)

    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.zxing.embedded)
    implementation(libs.coil.compose)

    testImplementation(libs.junit)
    testImplementation(libs.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
}
```

### 6.6 `gradle.properties`

```properties
org.gradle.jvmargs=-Xmx3g -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
kotlin.code.style=official
android.useAndroidX=true
android.nonTransitiveRClass=true
```

### 6.7 `local.properties` (machine-specific, commit pannaadhu)

```properties
sdk.dir=C\:\\Users\\devar\\AppData\\Local\\Android\\Sdk
```

### 6.8 `.gitignore`

```
.gradle/
build/
app/build/
local.properties
keystore.properties
*.jks
*.keystore
.idea/
*.iml
captures/
.cxx/
app/src/main/assets/models/*.gguf
app/src/main/assets/piper/*.onnx
```

### 6.9 Wrapper bootstrap (Gradle global illa)

**Option A — winget:**
```powershell
winget install --id Gradle.Gradle -e
cd "C:\Users\devar\Desktop\MAYA AI PROJECT\MOBILE APP"
gradle wrapper --gradle-version 8.11.1
```

**Option B — manual zip:**
```powershell
$dst = "$env:TEMP\gradle-8.11.1-bin.zip"
Invoke-WebRequest "https://services.gradle.org/distributions/gradle-8.11.1-bin.zip" -OutFile $dst
Expand-Archive $dst "$env:TEMP\gradle-8.11.1" -Force
cd "C:\Users\devar\Desktop\MAYA AI PROJECT\MOBILE APP"
& "$env:TEMP\gradle-8.11.1\gradle-8.11.1\bin\gradle.bat" wrapper --gradle-version 8.11.1
```

**Check:**
```powershell
.\gradlew.bat --version
```

---

## 7. App folder structure (file-by-file)

```
app\src\main\
├─ AndroidManifest.xml
├─ assets\
│  ├─ persona\maya.md              ← copy of MAYA AI\persona\girlfriend.md
│  ├─ persona\teacher.md           ← copy of MAYA AI\persona\english-teacher.md
│  └─ licenses\                    ← open-source notices
├─ res\
│  ├─ values\strings.xml           ← ALL English UI text
│  ├─ values\themes.xml            ← splash + base theme
│  ├─ values\colors.xml
│  ├─ drawable\ic_launcher_foreground.xml
│  ├─ mipmap-*\ic_launcher.png
│  ├─ xml\accessibility_service.xml
│  ├─ xml\network_security_config.xml
│  ├─ xml\file_paths.xml
│  └─ xml\backup_rules.xml
└─ java\com\devaraj\maya\
   ├─ MayaApp.kt                   ← Application, AppContainer init
   ├─ MainActivity.kt              ← single activity, Compose host
   ├─ di\AppContainer.kt           ← manual DI (db, api, repos, vault)
   ├─ core\
   │  ├─ Constants.kt              ← port, paths, limits
   │  ├─ Logger.kt                 ← local logs only, no personal data
   │  ├─ Result.kt                 ← AppResult<T> (Ok/Err)
   │  └─ Time.kt
   ├─ domain\model\
   │  ├─ Device.kt
   │  ├─ Message.kt
   │  ├─ Conversation.kt
   │  ├─ ConnectionState.kt
   │  ├─ AiSource.kt
   │  ├─ PcAction.kt
   │  ├─ MonitorSnapshot.kt
   │  └─ PermissionStatus.kt
   ├─ data\
   │  ├─ local\
   │  │  ├─ MayaDatabase.kt
   │  │  ├─ Converters.kt
   │  │  ├─ entity\ConversationEntity.kt
   │  │  ├─ entity\MessageEntity.kt
   │  │  ├─ entity\DeviceEntity.kt
   │  │  ├─ entity\PcCommandEntity.kt
   │  │  ├─ entity\NotificationEntity.kt
   │  │  ├─ entity\AuditEntity.kt
   │  │  └─ dao\ConversationDao.kt / MessageDao.kt / DeviceDao.kt
   │  │        / PcCommandDao.kt / NotificationDao.kt / AuditDao.kt
   │  ├─ prefs\SettingsStore.kt    ← DataStore
   │  ├─ secure\TokenVault.kt      ← Keystore AES-GCM
   │  ├─ remote\
   │  │  ├─ ApiClient.kt
   │  │  ├─ MayaApi.kt
   │  │  ├─ Dto.kt
   │  │  ├─ ChatSocket.kt
   │  │  ├─ EventsSocket.kt
   │  │  ├─ DiscoveryClient.kt     ← NSD `_maya._tcp`
   │  │  ├─ PrivateNetworkInterceptor.kt
   │  │  └─ ErrorMapper.kt
   │  └─ repo\
   │     ├─ ChatRepository.kt
   │     ├─ PairingRepository.kt
   │     ├─ ConnectionRepository.kt
   │     ├─ MonitorRepository.kt
   │     ├─ LaptopControlRepository.kt
   │     ├─ PhoneControlRepository.kt
   │     └─ SettingsRepository.kt
   ├─ ai\
   │  ├─ LlamaBridge.kt            ← external fun (JNI)
   │  ├─ LocalChatEngine.kt
   │  ├─ ModelManager.kt
   │  └─ PromptBuilder.kt
   ├─ voice\
   │  ├─ SpeechRecognizerManager.kt
   │  ├─ AndroidTts.kt
   │  ├─ PiperTts.kt
   │  └─ VoicePipeline.kt
   ├─ control\phone\
   │  ├─ AppController.kt
   │  ├─ AccessibilityController.kt
   │  ├─ NotificationCollector.kt
   │  ├─ SmsController.kt
   │  ├─ CallController.kt
   │  ├─ FileController.kt
   │  ├─ PermissionChecker.kt
   │  └─ AuditLog.kt
   ├─ service\
   │  ├─ MayaForegroundService.kt
   │  ├─ WakeDetector.kt
   │  ├─ ClapDetector.kt
   │  └─ BootReceiver.kt
   └─ ui\
      ├─ theme\Color.kt / Type.kt / Shape.kt / Dimens.kt / Theme.kt
      ├─ components\
      │  ├─ MayaTopBar.kt
      │  ├─ ConnectionChip.kt
      │  ├─ MessageBubble.kt
      │  ├─ VoiceOrb.kt
      │  ├─ StatusCard.kt
      │  ├─ Sparkline.kt
      │  ├─ ConfirmDialog.kt
      │  ├─ PermissionCard.kt
      │  ├─ SectionHeader.kt
      │  ├─ EmptyState.kt
      │  └─ PrimaryButton.kt
      ├─ navigation\Routes.kt / MayaNavHost.kt / BottomBar.kt
      ├─ onboarding\OnboardingScreen.kt
      ├─ pairing\PairingScreen.kt / PairingViewModel.kt / QrScannerScreen.kt
      ├─ chat\ChatScreen.kt / ChatViewModel.kt
      ├─ voice\VoiceScreen.kt / VoiceViewModel.kt
      ├─ laptop\LaptopControlScreen.kt / LaptopControlViewModel.kt
      ├─ phone\PhoneControlScreen.kt / PhoneControlViewModel.kt
      │  └─ sections\AppsSection.kt / MessagesSection.kt
      │       / NotificationsSection.kt / FilesSection.kt / ScreenSection.kt
      ├─ monitor\MonitorScreen.kt / MonitorViewModel.kt
      └─ settings\SettingsScreen.kt / SettingsViewModel.kt
         / AppearanceScreen.kt / ConnectionSettingsScreen.kt
         / AiSettingsScreen.kt / VoiceSettingsScreen.kt
         / PermissionsScreen.kt / PrivacyScreen.kt / AboutScreen.kt
```

---

## 8. Android Manifest spec

### 8.1 Permissions

```xml
<!-- Network (LAN only) -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
<uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />

<!-- Voice + background -->
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />

<!-- Phone control -->
<uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" />
<uses-permission android:name="android.permission.READ_SMS" />
<uses-permission android:name="android.permission.SEND_SMS" />
<uses-permission android:name="android.permission.RECEIVE_SMS" />
<uses-permission android:name="android.permission.READ_PHONE_STATE" />
<uses-permission android:name="android.permission.CALL_PHONE" />
<uses-permission android:name="android.permission.READ_CONTACTS" />
<uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
<uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />
<uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />

<!-- UI -->
<uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
<uses-permission android:name="android.permission.VIBRATE" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.USE_BIOMETRIC" />

<uses-feature android:name="android.hardware.camera" android:required="false" />
<uses-feature android:name="android.hardware.microphone" android:required="true" />
```

**NOT used:** `MANAGE_EXTERNAL_STORAGE` (Play policy + risky). Files = SAF / MediaStore.

### 8.2 Application block

```xml
<application
    android:name=".MayaApp"
    android:allowBackup="false"
    android:dataExtractionRules="@xml/backup_rules"
    android:fullBackupContent="false"
    android:icon="@mipmap/ic_launcher"
    android:label="@string/app_name"
    android:networkSecurityConfig="@xml/network_security_config"
    android:supportsRtl="true"
    android:theme="@style/Theme.MayaAI"
    android:enableOnBackInvokedCallback="true"
    android:usesCleartextTraffic="true">

    <activity
        android:name=".MainActivity"
        android:exported="true"
        android:launchMode="singleTask"
        android:windowSoftInputMode="adjustResize">
        <intent-filter>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent-filter>
    </activity>

    <service
        android:name=".control.phone.AccessibilityController"
        android:exported="false"
        android:label="@string/accessibility_label"
        android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">
        <intent-filter>
            <action android:name="android.accessibilityservice.AccessibilityService" />
        </intent-filter>
        <meta-data
            android:name="android.accessibilityservice"
            android:resource="@xml/accessibility_service" />
    </service>

    <service
        android:name=".control.phone.NotificationCollector"
        android:exported="false"
        android:label="@string/notification_listener_label"
        android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
        <intent-filter>
            <action android:name="android.service.notification.NotificationListenerService" />
        </intent-filter>
    </service>

    <service
        android:name=".service.MayaForegroundService"
        android:exported="false"
        android:foregroundServiceType="microphone" />

    <receiver
        android:name=".service.BootReceiver"
        android:exported="false">
        <intent-filter>
            <action android:name="android.intent.action.BOOT_COMPLETED" />
        </intent-filter>
    </receiver>

    <provider
        android:name="androidx.core.content.FileProvider"
        android:authorities="${applicationId}.files"
        android:exported="false"
        android:grantUriPermissions="true">
        <meta-data
            android:name="android.support.FILE_PROVIDER_PATHS"
            android:resource="@xml/file_paths" />
    </provider>
</application>
```

### 8.3 `xml/accessibility_service.xml`

```xml
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeAllMask"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows|flagIncludeNotImportantViews"
    android:canPerformGestures="true"
    android:canRetrieveWindowContent="true"
    android:description="@string/accessibility_description"
    android:notificationTimeout="100" />
```

### 8.4 `xml/network_security_config.xml`

```xml
<network-security-config>
    <!-- LAN HTTP only. No public host allowed by app code. -->
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
```

### 8.5 `values/themes.xml` + `values/colors.xml`

```xml
<resources>
    <style name="Theme.MayaAI" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@color/maya_background</item>
        <item name="android:statusBarColor">@android:color/transparent</item>
        <item name="android:navigationBarColor">@android:color/transparent</item>
        <item name="android:windowLightStatusBar">false</item>
        <item name="android:windowSplashScreenBackground">@color/maya_background</item>
        <item name="android:windowSplashScreenAnimatedIcon">@mipmap/ic_launcher</item>
        <item name="android:windowSplashScreenIconBackgroundColor">@color/maya_background</item>
    </style>
</resources>
```

```xml
<resources>
    <color name="maya_background">#0B0B10</color>
    <color name="maya_primary">#B388FF</color>
</resources>
```

### 8.6 `xml/backup_rules.xml`

```xml
<data-extraction-rules>
    <cloud-backup>
        <exclude domain="root" path="." />
    </cloud-backup>
    <device-transfer>
        <exclude domain="root" path="." />
    </device-transfer>
</data-extraction-rules>
```

---

## 9. Design system

### 9.1 Colors — Dark (default)

| Token | Value |
|---|---|
| `background` | `#0B0B10` |
| `surface` | `#14141C` |
| `surfaceHigh` | `#1D1D28` |
| `primary` | `#B388FF` |
| `secondary` | `#64B5F6` |
| `accent` | `#FF80AB` |
| `onBackground` | `#ECEAF4` |
| `onSurfaceVariant` | `#A8A4B8` |
| `success` | `#4ADE80` |
| `warning` | `#FBBF24` |
| `error` | `#F87171` |
| `outline` | `#2E2E3C` |

### 9.2 Colors — Light

| Token | Value |
|---|---|
| `background` | `#F7F6FB` |
| `surface` | `#FFFFFF` |
| `surfaceHigh` | `#EFEDF7` |
| `primary` | `#6C4BC4` |
| `secondary` | `#1976D2` |
| `accent` | `#D81B60` |
| `onBackground` | `#17151F` |
| `onSurfaceVariant` | `#5B5769` |
| `success` | `#15803D` |
| `warning` | `#B45309` |
| `error` | `#B91C1C` |
| `outline` | `#DAD6E8` |

**Dynamic color:** OFF (brand look maintain panna).

### 9.3 Typography (Material 3 defaults)

| Style | Size / weight |
|---|---|
| displaySmall | 32 / 400 |
| headlineMedium | 26 / 600 |
| titleLarge | 20 / 600 |
| titleMedium | 16 / 600 |
| bodyLarge | 16 / 400 |
| bodyMedium | 14 / 400 |
| labelLarge | 14 / 500 |
| labelSmall | 11 / 500 |

Font: system sans (Roboto). Offline — no font download.

### 9.4 Shape / spacing

| Item | Value |
|---|---|
| Card radius | 20 dp |
| Button radius | 16 dp |
| Bubble radius | 18 dp (tail corner 4 dp) |
| Dialog radius | 24 dp |
| Screen padding | 16 dp |
| List gap | 8 dp |
| Section gap | 24 dp |

### 9.5 Components (reusable)

| Component | Purpose |
|---|---|
| `MayaTopBar` | Title + connection chip + settings gear |
| `ConnectionChip` | Connected / Connecting / Offline |
| `MessageBubble` | User / Maya / error bubble |
| `VoiceOrb` | Animated mic orb + state ring |
| `StatusCard` | Metric label + value + progress bar |
| `Sparkline` | 60-point history canvas |
| `ConfirmDialog` | Action description + Cancel / Allow |
| `PermissionCard` | Permission status + Open settings |
| `SectionHeader` | Section title + optional action |
| `EmptyState` | Icon + title + hint |
| `PrimaryButton` | Gradient primary button |

---

## 10. Navigation

Routes (`Routes.kt`):

```
onboarding
pairing
pairing/qr
main/chat
main/voice
main/laptop
main/phone
main/monitor
main/settings
settings/appearance
settings/connection
settings/ai
settings/voice
settings/permissions
settings/privacy
settings/about
```

- Bottom nav: **6 items** — Chat, Voice, Laptop, Phone, Monitor, Settings.
- Small screens (< 360 dp): Settings-ah top-bar gear-ku move pannalam (optional fallback).
- Pairing / onboarding = full-screen, bottom nav illa.
- Back: `NavHost` default. Chat-la back = app exit (single task).

---

## 11. Screens — detailed spec

### 11.1 Onboarding

Purpose: privacy + permissions explain, pairing skip option.

Content:
1. **Welcome** — Maya name, one-line "Local-first assistant".
2. **Privacy** — 3 bullet: no cloud, no ads, data phone-la.
3. **Permissions** — what needs what (mic, notifications, accessibility, SMS).
4. Buttons: **Continue** → pairing; **Skip for now** → chat (phone mode).

State: `onboarding_done` DataStore flag.

### 11.2 Pairing

Sections:
1. **Find laptop** — NSD discovery list (auto), "Enter IP manually", "Scan QR".
2. **PIN entry** — 6 boxes, auto-submit, error + attempts left.
3. **Pairing** — spinner.
4. **Success** — laptop name + "Start chatting".

States:
`Idle` → `Discovering` → `DeviceFound(list)` → `PinEntry` / `Scanning` → `Claiming` → `Connected` / `Failed(reason)`.

Failure messages (English):
- "Laptop not found. Check same Wi-Fi."
- "Wrong PIN. 3 tries left."
- "PIN expired. Ask laptop for a new code."
- "Pairing locked. Try again in 10 minutes."

Auto-connect setting: Settings → Connection → toggle.

### 11.3 Chat

Header: "Maya" + `ConnectionChip` + persona chip (`Maya` / `Teacher`) + menu.
Body: message list (reverse), date separators, streaming cursor.
Empty state: greeting card + 4 suggestion chips.
Composer: text field, mic button, send button. Enter = send (hardware keyboard).
Menu: New chat, Clear chat, Copy last reply.

Message bubble:
- User = primary tint right aligned.
- Maya = surface left aligned.
- Error = error tint + Retry.
- Long press = Copy / Delete.
- Show source label: `Laptop` / `Phone` / `—`.

States:
- Sending → spinner on bubble.
- Streaming → tokens append.
- Laptop offline + phone model not downloaded → banner "Start Maya on laptop or download the phone model."

### 11.4 Voice

- Big `VoiceOrb` (idle / listening / thinking / speaking).
- Tap = listen until silence (max 15 s). Hold = push-to-talk.
- Live transcript below orb.
- After reply: TTS auto-play (toggle).
- Engine row: STT `Android` / `Laptop`; TTS `Android` / `Piper`.
- Recent transcripts list (last 10, local only).
- Permission card if mic denied.

### 11.5 Laptop Control

- Status header: laptop name, connection mode, latency.
- Quick actions grid (2 columns): Open app, Close app, Run command, Read file, List files, Lock, Volume, Screenshot, Media, Clipboard.
- Command builder: action dropdown + params + **Send**.
- Pending confirmation dialog (from `needs_confirmation`).
- Activity log: last 50 commands with status.
- Offline state: "Connect to laptop" button.

Every `ask` action → `ConfirmDialog` first. Server confirm token use pannum.

### 11.6 Phone Control

Top: **Master switch** — "Maya control" ON/OFF (persistent notification).
Permission dashboard cards:
| Card | Opens |
|---|---|
| Accessibility | System accessibility settings |
| Notification access | Notification listener settings |
| SMS | Runtime permission |
| Phone | Runtime permission |
| Contacts | Runtime permission |
| Files | SAF picker |
| Battery optimization | Ignore battery settings |
| Overlay | Appear-on-top settings |

Sections (tabs):
1. **Apps** — installed app list (search), tap → open, long press → app info.
2. **Messages** — conversation list (READ_SMS), send SMS with confirmation.
3. **Notifications** — last 100 (local), tap → open app.
4. **Files** — SAF tree picker, list, open, share.
5. **Screen** — enable accessibility, "Read screen" (show text), "Tap text", "Scroll", "Back/Home/Recents".

Rules:
- Screen actions only when unlocked (default).
- SMS / call / delete → confirmation.
- Audit log locally (last 200).
- Android 13+ sideloaded accessibility restriction note (see §19.6).

### 11.7 Monitoring

Tabs: **Laptop** / **Phone**.

Laptop cards: CPU %, RAM, GPU, NPU, battery, temp, disk, uptime, latency.
Phone cards: battery, storage, RAM, network type, uptime.

- Update: `GET /pc/status` every 2 s while visible + WS events when connected.
- Sparkline 60 samples.
- Pause when screen not visible (lifecycle).
- Null values show "—".

### 11.8 Settings

Sections:

**Appearance**
- Theme: Dark / Light / System (default System)
- Text size: Small / Default / Large
- Chat bubble style: default only (v1)

**Connection**
- Mode: WiFi / USB / Bluetooth PAN
- Laptop IP + port (manual)
- Auto-connect toggle (default off)
- Pair new laptop / Revoke devices
- Test connection

**AI**
- Mode: Auto / Laptop only / Phone only
- Laptop model info
- Phone model: download/import, size, delete
- Persona default: Maya / Teacher

**Voice**
- STT: Android / Laptop (default Auto)
- TTS: Android / Piper (default Android)
- Voice picker, speed slider 0.5–2.0
- Wake: OFF by default; clap toggle; "Maya" x3 toggle (battery warning)

**Permissions**
- Live status of all permissions with "Open settings"

**Privacy**
- "No cloud. No telemetry." statement
- Export chat history (JSON, SAF)
- Delete all local data (double confirm)
- Screen lock (biometric) optional

**About**
- Version, build, API level
- Open-source licenses
- Laptop API compatibility
- App log export (no personal content)

---

## 12. Data layer

### 12.1 Room schema (v1)

```sql
CREATE TABLE conversations (
    id TEXT NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    persona TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE messages (
    id TEXT NOT NULL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    model TEXT,
    error TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX idx_messages_conv_created ON messages(conversation_id, created_at);

CREATE TABLE devices (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    auto_connect INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE pc_commands (
    id TEXT NOT NULL PRIMARY KEY,
    action TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE notifications (
    id TEXT NOT NULL PRIMARY KEY,
    package_name TEXT NOT NULL,
    title TEXT,
    body TEXT,
    posted_at INTEGER NOT NULL,
    important INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_notifications_posted ON notifications(posted_at);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
```

Models: `ConversationEntity`, `MessageEntity`, `DeviceEntity`, `PcCommandEntity`, `NotificationEntity`, `AuditEntity`.

DAOs:
- `ConversationDao`: insert, observeAll, observeById, updateTitle, delete, deleteAll.
- `MessageDao`: insert, updateContentStatus, observeByConversation, deleteByConversation, deleteAll, lastN.
- `DeviceDao`: upsert, observeAll, delete, touch.
- `PcCommandDao`: insert, updateStatus, observeRecent(50), deleteAll.
- `NotificationDao`: insert, observeRecent(100), deleteOlderThan(days), deleteAll.
- `AuditDao`: insert, observeRecent(200), deleteAll.

DB: `MayaDatabase` version 1, `exportSchema = true`, schema folder `app/schemas/`.

### 12.2 DataStore keys

| Key | Type | Default |
|---|---|---|
| `theme` | String | `system` |
| `text_size` | String | `default` |
| `onboarding_done` | Boolean | false |
| `connection_mode` | String | `wifi` |
| `laptop_host` | String | `""` |
| `laptop_port` | Int | 8420 |
| `auto_connect` | Boolean | false |
| `device_id` | String | generated UUID |
| `device_name` | String | Build.MODEL |
| `ai_mode` | String | `auto` |
| `persona` | String | `maya` |
| `stt_engine` | String | `auto` |
| `stt_lang` | String | `en-IN` |
| `tts_engine` | String | `android` |
| `tts_voice` | String | system default |
| `tts_speed` | Float | 1.0 |
| `tts_auto_play` | Boolean | true |
| `wake_enabled` | Boolean | false |
| `clap_enabled` | Boolean | false |
| `control_enabled` | Boolean | false |
| `control_require_unlock` | Boolean | true |
| `lock_screen_biometric` | Boolean | false |
| `model_imported` | Boolean | false |
| `model_path` | String | `""` |
| `last_conversation_id` | String | `""` |
| `privacy_export_path` | String | `""` |

### 12.3 Repositories

| Repository | Responsibility |
|---|---|
| `SettingsRepository` | DataStore read/write, defaults |
| `PairingRepository` | PIN/QR claim, refresh, revoke, token save |
| `ConnectionRepository` | Active device, health poll, WS lifecycle, state flow |
| `ChatRepository` | Save message, choose source, call WS/REST/local |
| `LaptopControlRepository` | Command send, confirm, cancel, status |
| `MonitorRepository` | Status poll + event stream → Flow |
| `PhoneControlRepository` | Apps, SMS, calls, notifications, files wrappers |

### 12.4 TokenVault (security)

- Android Keystore alias `maya_token_key` — AES-256-GCM.
- File: `filesDir/secure/token_<device_id>.bin` (IV + ciphertext).
- Methods: `save(deviceId, token)`, `load(deviceId)`, `delete(deviceId)`, `deleteAll()`.
- Never log token. Never Room. Never backup (`allowBackup=false`).

### 12.5 Identifiers

- Message ID: `m_<UUIDv4>`.
- Conversation ID: `c_<UUIDv4>`.
- Command ID: `p_<UUIDv4>`.
- Device ID: Android `Settings.Secure.ANDROID_ID` hashed + random suffix (32 hex).

---

## 13. Network layer

### 13.1 `ApiClient`

- OkHttp: connect 5 s, read 60 s (chat), write 30 s, ping 10 s.
- Interceptor 1: `PrivateNetworkInterceptor` — host resolve; private IP mattum allow. Public → `IOException("blocked: non-local host")`.
- Interceptor 2: Auth — token from `TokenVault`, add `Authorization`.
- Interceptor 3: Debug logging (`BuildConfig.DEBUG` only; header redact).
- Retrofit + kotlinx.serialization converter.
- Base URL set per active device: `http://<host>:<port>/api/v1/`.

### 13.2 `MayaApi` (REST)

```kotlin
suspend fun health(): HealthDto
suspend fun pairClaim(body: PairClaimRequest): PairResponse
suspend fun pairQrClaim(body: QrClaimRequest): PairResponse
suspend fun pairRefresh(body: RefreshRequest): RefreshResponse
suspend fun listDevices(): DevicesDto
suspend fun revokeDevice(id: String): RevokeDto
suspend fun chat(body: ChatRequest): ChatResponse
suspend fun stt(audio: RequestBody, lang: String): SttResponse
suspend fun tts(body: TtsRequest): ResponseBody
suspend fun voiceStatus(): VoiceStatusDto
suspend fun pcStatus(): PcStatusDto
suspend fun pcCommand(body: PcCommandRequest): PcCommandResponse
suspend fun pcConfirm(token: String): PcCommandResponse
suspend fun pcCancel(token: String): CancelDto
suspend fun wakeStatus(): WakeStatusDto
suspend fun wakeListen(seconds: Int): WakeStatusDto
suspend fun wakeStop(): WakeStatusDto
```

### 13.3 WebSockets

`ChatSocket`:
- URL `ws://host:port/api/v1/ws/chat`
- Header `Authorization`; query `?token=` fallback (server support).
- Events sealed class: `Start`, `Token(text)`, `Done`, `Error`.
- `send(messages, persona)`; `cancel()` closes + reconnect.
- Reconnect: only on unexpected close; 1/2/4/8/16/30 s backoff.
- Ping every 25 s.

`EventsSocket`:
- URL `/api/v1/ws/events`.
- Emits `Status(data)`, `Wake(state)`, `Notification(title, body)`, `Server(state)`.
- Only active when app foreground + monitor/laptop screen visible or wake enabled.

### 13.4 Discovery

- `NsdManager` service type `_maya._tcp.`
- Resolve → host + port.
- Manual IP fallback.
- USB: host `127.0.0.1` port 8420 (laptop `adb reverse tcp:8420 tcp:8420`).
- BT PAN: same discovery on PAN interface.

### 13.5 Error mapping

| Situation | UI |
|---|---|
| 1003 | "Wrong PIN" + attempts |
| 1004 | "Code expired — get a new one" |
| 1005 | "Too many tries — wait" |
| 1007 | "Device removed — pair again" |
| 3001 | "Maya engine is not running on laptop" |
| 3002 | "Laptop took too long — retry" |
| 4002/4003 | "Action not allowed" |
| Timeout | "No response from laptop" |
| Non-local host | "Only local network allowed" |

---

## 14. Pairing + connection

### 14.1 Pairing state machine

```
Idle
 └─ startDiscovery() → Discovering
      ├─ found(device) → DeviceSelected
      ├─ user enters IP → PinEntry
      └─ scan QR → Scanning
 PinEntry → claimPin() → Claiming
 Scanning → claimQr()  → Claiming
 Claiming → success → Connected(device, token)
          → failure → Failed(reason) → Idle / PinEntry
```

### 14.2 Connection manager

- On app start: load last device + token → health check (2 s timeout).
- Success → `Connected`, start chat socket lazily.
- Fail → `Disconnected`; auto-connect ON-a irundhaa 3 tries (2 s, 5 s, 10 s).
- Network change receiver → re-check.
- `last_seen` update every 60 s.

### 14.3 Pairing UI rules

- PIN boxes 6, numeric keyboard, paste support.
- QR scanner uses ZXing embedded (offline, no Play Services).
- Show laptop name after success.
- Never show token.

---

## 15. Chat pipeline

```
User text
  → save Message(status=SENDING)
  → choose source:
      laptop connected? → ChatSocket
      else phone model ready? → LocalChatEngine
      else → show setup banner
  → on first token: status=STREAMING
  → on done: status=SENT, source saved
  → on error: status=FAILED, error saved
```

Rules:
- Send last 24 messages only, max 12 000 chars.
- Persona prompt server-side (laptop) / local prompt builder (phone).
- No automatic retry for chat (duplicate risk). UI "Retry" button.
- New chat → new conversation row.
- Title = first 40 chars of first user message.
- Streaming update = in-place DB update every 250 ms (not every token) to avoid jank.
- Cancel = close socket + mark partial message `SENT (stopped)`.

Persona prompt (phone) = same text as `MAYA AI\persona\girlfriend.md` / `english-teacher.md`, bundled in assets. Copy at build time; runtime-la project path use pannaadhu.

---

## 16. Voice pipeline

### 16.1 STT

- Primary: `SpeechRecognizer` + `EXTRA_PREFER_OFFLINE=true`.
- Language: `en-IN` default; `ta-IN` option.
- Max 15 s, silence auto-stop.
- If unavailable: record WAV 16 kHz mono → laptop `/voice/stt` (only if connected).
- No cloud STT.

### 16.2 TTS

- Default: Android `TextToSpeech` (system English voice).
- Piper: sherpa-onnx AAR + voice model (Tamil/English) stored in `filesDir/piper/`.
- Voice model download = manual import (SAF) or user-provided URL (Wi-Fi only, explicit).
- Speed slider 0.5–2.0.
- Stop speaking when mic pressed (barge-in).

### 16.3 Voice screen states

```
Idle → Listening → Transcribing → Thinking → Speaking → Idle
                     ↓ error
                   Error(message)
```

Wake triggers phone-la:
- Clap x3 (AudioRecord amplitude peaks) — default OFF.
- "Maya" x3 — Vosk small model, default OFF, battery warning.
- Wake aanaa → open app + Voice screen + start listening.

---

## 17. On-device AI

### 17.1 Model

- tamil-lm-2b Instruct (`Timegravity/tamil-lm-2b-instruct`), Q4_K_M GGUF
  (~1.3 GB). Qwen3.5-2B base tuned for Tamil / Tanglish.
- Location: `filesDir/models/tamil-lm-2b-instruct-q4_k_m.gguf`.
- A model imported before this switch (`qwen3-1.7b-instruct-q4_k_m.gguf`) is
  still loadable and is deleted on the next import.
- Import via SAF (user downloads on laptop, transfers via USB).
- Verify: file size > 500 MB + GGUF magic `GGUF`.
- Delete option in Settings.

### 17.2 Native build (Phase 9)

- NDK 27.2.12479018, CMake 3.22.1.
- Vendor llama.cpp source at `app/src/main/cpp/llama.cpp/` (pinned tag; record in `libs.versions.toml` comment).
- Build ABIs: `arm64-v8a` (primary), `x86_64` (emulator).
- CMake flags: tests/examples OFF, shared libs.
- Wrapper: `app/src/main/cpp/maya_llama.cpp`.

JNI API:

```kotlin
object LlamaBridge {
    external fun loadModel(path: String, nThreads: Int, nCtx: Int): Long
    external fun generate(handle: Long, prompt: String, maxTokens: Int,
                          temperature: Float, topP: Float, topK: Int,
                          callback: (String) -> Unit): Int
    external fun cancel(handle: Long)
    external fun freeModel(handle: Long)
}
```

- `loadModel` once, mutex-protected.
- Generation on `Dispatchers.Default` single thread.
- `onTrimMemory(TRIM_MEMORY_RUNNING_LOW)` → unload, keep path.
- Prompt template: ChatML (`<|im_start|>user ... <|im_end|>`), per Qwen3 card.
- Params: temp 0.7, top_p 0.9, top_k 40, repeat_penalty 1.1, n_ctx 4096.
- Stop on user cancel / screen destroy.

### 17.3 Device requirement

- 6 GB RAM recommended, 4 GB minimum (might be slow).
- 3 GB free storage.
- First token target < 5 s on mid-range phone.

### 17.4 Fallback policy

| Laptop | Phone model | Result |
|---|---|---|
| Connected | any | Laptop |
| Offline | Ready | Phone |
| Offline | Not ready | Banner + setup |

User override in Settings (Laptop only / Phone only).

---

## 18. Phone control (detailed)

### 18.1 Master switch

- `control_enabled` DataStore.
- ON → foreground notification "Maya control active" with **Pause** action.
- OFF → all control actions blocked.

### 18.2 Apps

- `PackageManager.queryIntentActivities` + `getInstalledApplications`.
- Launch: `getLaunchIntentForPackage` → `startActivity`.
- Close: not generally possible (Android restriction). Offer "force stop" only via accessibility (not reliable) → v1 shows info page instead.
- App info: `ACTION_APPLICATION_DETAILS_SETTINGS`.

### 18.3 Accessibility (screen)

- Events stored in memory ring buffer (last 50).
- Read screen: traverse `AccessibilityNodeInfo`, return visible text + view IDs.
- Actions: `ACTION_CLICK` by text, `GLOBAL_ACTION_BACK/HOME/RECENTS`, scroll via gesture.
- Limits: secure windows (banking) → no content. Show "This screen is protected".
- Require device unlocked (setting, default true).

### 18.4 Notifications

- `NotificationListenerService` → insert into Room (max 100).
- Ignore own app notifications.
- "Important" = priority HIGH or category ALARM/CALL/MESSAGE.
- No content leaves phone except explicit user chat command.

### 18.5 SMS

- Read: `content://sms/inbox` (READ_SMS).
- Send: `SmsManager.sendTextMessage` after `ConfirmDialog`.
- Multi-SIM: default SIM; show SIM if dual.
- Never auto-send. Ever.

### 18.6 Calls

- `ACTION_CALL` with `CALL_PHONE`; confirm dialog.
- Unknown number → show number.
- Contacts name resolution if `READ_CONTACTS`.

### 18.7 Files

- SAF `OpenDocumentTree` for user-selected folder.
- Persist URI permission.
- List/open/share only inside selected tree.
- No `MANAGE_EXTERNAL_STORAGE`.

### 18.8 Audit

- Every control action → `audit_log` row (allowed true/false, detail).
- Settings → Privacy → "Control activity" screen (last 200).

### 18.9 Sideload restrictions (important)

Android 13+ sideloaded apps need:
`Settings → Apps → Maya AI → ⋮ → Allow restricted settings`
before enabling Accessibility / Notification access.

App must show this exact hint + button to app info screen. Without it, toggle is greyed out.

---

## 19. Laptop control (app side)

- Only when connected.
- Action list from API contract §9.5 (hardcode enum + labels).
- Flow:
  1. User picks action + params.
  2. `POST /pc/command`.
  3. `needs_confirmation` → `ConfirmDialog` (description + 60 s timer).
  4. Allow → `POST /pc/confirm`; Cancel → `POST /pc/cancel`.
  5. Result → log + snackbar.
- `denied` → red snackbar, no retry.
- Read-only actions execute directly.
- File picker for `file.*` paths? Phone-la direct laptop path type pannum (v1). Later browse API.

---

## 19A. Phone remote (laptop controls phone)

**New feature** — Laptop UI controls paired phone (screen view + input + files).

### 19A.1 Phone side requirements

**Screen capture (MediaProjection):**
- `MediaProjectionManager.createScreenCaptureIntent()` → user grants permission
- `VirtualDisplay` + `ImageReader` → capture frames as JPEG
- Stream via WebSocket or HTTP MJPEG to laptop
- Config: max_width (default 1280), quality (default 60), fps (default 10)

**Input injection (AccessibilityService):**
- Reuse existing `MayaAccessibilityService.kt` (§18.3)
- Expose internal methods: `click(x,y)`, `swipe(x1,y1,x2,y2)`, `type(text)`, `key(keycode)`, `scroll(dx,dy)`, `back()`, `home()`, `recents()`
- Secure window check → reject input on protected screens

**API endpoints on phone (HTTP + WebSocket):**
- `POST /phone/remote/start` — start session, returns session_token + WebSocket URL
- `POST /phone/remote/stop` — stop session
- `POST /phone/remote/input` — inject input events (requires session_token)
- `GET /phone/remote/screen` — MJPEG stream (alternative to WS)
- `WS /phone/remote/ws` — binary frames (JPEG) + input ack
- `POST /phone/remote/files` — file browse/download/upload (SAF, within allowed roots)

**Session management:**
- Short-lived tokens (5 min default, sliding expiry)
- User confirmation required on phone before session starts
- Phone shows persistent notification "Remote control active" with Stop button
- Only one active session per paired laptop

**Permissions:**
- `FOREGROUND_SERVICE_MEDIA_PROJECTION` (Android 14+)
- `BIND_ACCESSIBILITY_SERVICE` (already in manifest)
- User must enable Accessibility + grant MediaProjection each session

### 19A.2 Laptop side requirements

**New UI page:** "Phone Remote" tab (visible only when phone connected)

**Features:**
- Screen view (live JPEG stream via WebSocket)
- Touch/click/drag on screen → sends input events
- On-screen keyboard → send text
- Hardware key buttons (Back, Home, Recents, Enter, Esc, Tab, arrows)
- File browser (phone allowed roots)
- Hybrid mode indicator (AI + user sharing control)
- Session start/stop with confirmation dialog

**Integration:**
- Uses existing pairing tokens
- Phone remote session separate from laptop remote session
- Settings toggle: "Allow laptop to control this phone"

---

## 20. Monitoring (app side)

## 20. Monitoring (app side)

- Laptop: poll 2 s while visible; WS events when available.
- Phone: `ActivityManager.MemoryInfo`, `BatteryManager`, `StatFs`, `SystemClock`.
- Charts: 60 samples (2 min at 2 s).
- Low/critical thresholds color: RAM > 85% warning, battery < 20% warning.
- Pause timers on `ON_STOP`.

---

## 21. Background service + wake

### 21.1 Foreground service

- Start only from app UI (Android 12+ restriction).
- Type: `microphone`.
- Notification channel `maya_service`, low importance.
- Actions: Pause, Stop.
- Stop on user Logout / control off / wake off.

### 21.2 Wake

- Clap detector: AudioRecord 16 kHz, peak > threshold (2600–3200), 3 claps in 3 s, cooldown 8 s.
- Name detector: Vosk small en-in model (~40 MB) continuous, matches "maya" 3 times in 5 s.
- Both OFF by default.
- On wake: vibrate 100 ms + open `MainActivity` + voice listening.

### 21.3 Battery rules

- Doze → pause listening; restart on `ACTION_USER_PRESENT` if enabled.
- Show battery impact warning first time.
- Auto-stop after 30 min continuous listening (config).

---

## 22. Settings — defaults

| Setting | Default |
|---|---|
| Theme | System |
| Text size | Default |
| Connection mode | WiFi |
| Auto-connect | Off |
| AI mode | Auto |
| Persona | Maya |
| STT | Auto (Android first) |
| STT language | English (India) |
| TTS | Android |
| TTS speed | 1.0 |
| Auto-play reply | On |
| Wake (clap / name) | Off (both) |
| Control master switch | Off |
| Require unlock for control | On |
| Biometric app lock | Off |
| Telemetry | None (no code) |

---

## 23. Privacy & security — hard rules

- No analytics SDK, no ads, no crash reporting to cloud.
- No Gemini / cloud AI calls from phone.
- `PrivateNetworkInterceptor` blocks public hosts.
- Token = Keystore AES-GCM, backup disabled.
- `allowBackup=false`, `dataExtractionRules` excludes everything.
- Logs: no message text, no phone numbers, no names.
- Screenshots of secure screens: optional `FLAG_SECURE` on pairing/settings.
- Chat history local only; delete = real delete.
- Permissions requested when user opens the feature, not at startup.
- Accessibility never used silently — persistent notification while active.
- No auto-send SMS, no auto-call, no auto-delete.

---

## 24. Build phases (with DoD)

### Phase 0 — Project setup

Tasks:
- Gradle wrapper bootstrap.
- All Gradle files per §6.
- `local.properties`.
- Manifest + launcher icon placeholder.
- MainActivity with "Maya AI" text.

**DoD:**
- `.\gradlew.bat assembleDebug` → BUILD SUCCESSFUL.
- `adb install` works (emulator/device).
- App opens without crash.

### Phase 1 — Theme + shell + navigation

Tasks:
- Theme (dark/light/system), typography, shapes.
- Bottom nav 6 items + placeholder screens.
- Top bar + connection chip (static).
- Onboarding 3 pages.

**DoD:**
- All 6 tabs navigate.
- Theme switch works live.
- Back stack correct.
- Onboarding flag persists (DataStore).

### Phase 2 — Data layer

Tasks:
- Room entities/DAOs/database.
- DataStore settings + defaults.
- TokenVault.
- Repositories with fake data.

**DoD:**
- Unit tests: DAO insert/read/delete, settings defaults, TokenVault save/load (instrumented).
- Chat history survives app restart.

### Phase 3 — Pairing + connection

Tasks:
- `MayaApi`, ApiClient, interceptors.
- Discovery (NSD) + manual IP.
- PIN flow + QR scan.
- Token refresh, revoke.
- Connection state + health polling.

**DoD:**
- Pair with real laptop server OR MockWebServer fixture.
- Wrong PIN → error + attempts.
- App restart → auto-connect (if enabled).
- Revoke → 401 → pairing screen.
- Public IP blocked.

### Phase 4 — Chat

Tasks:
- Chat UI + streaming.
- ChatRepository + source selection.
- Conversation list/new chat/delete.
- Persona switch.

**DoD:**
- End-to-end chat with laptop (streaming visible).
- Messages persist after restart.
- Cancel streaming works.
- Error state + retry works.
- 24-message limit respected.

### Phase 5 — Voice

Tasks:
- Android STT.
- Android TTS + speed/voice.
- Voice screen + orb animation.
- Optional laptop STT fallback.

**DoD:**
- Speak → text appears → reply spoken.
- Mic denied → permission card.
- Stop speaking works.

### Phase 6 — Phone control

Tasks:
- Master switch + notification.
- Apps list/open.
- Accessibility service + read screen + basic actions.
- Notification listener.
- SMS read/send (confirm).
- Calls (confirm).
- SAF files.
- Audit log + activity screen.
- Restricted settings hint.

**DoD:**
- Each feature manual test passes.
- SMS/call require confirm.
- Control off → all blocked.
- Audit rows written.

### Phase 7 — Laptop control

Tasks:
- Actions UI.
- Command → confirm → execute flow.
- Activity log.

**DoD:**
- `app.open` with confirm works.
- Cancel → action not executed.
- Denied action shows message.
- Confirm token expiry handled.

### Phase 8 — Monitoring

Tasks:
- Laptop cards + polling.
- Phone cards.
- Sparklines.
- Events WS (optional).

**DoD:**
- Values match laptop within tolerance.
- No polling when screen hidden.
- Null handling correct.

### Phase 9 — On-device model

Tasks:
- NDK/CMake + llama.cpp.
- JNI wrapper.
- Model import + verify.
- Local chat + prompt builder.
- Fallback logic.

**DoD:**
- Model loads on arm64 device/emulator.
- Reply generated offline (airplane mode).
- Cancel + unload works.
- No crash on low memory.

### Phase 10 — Background + wake

Tasks:
- Foreground service.
- Clap detector.
- Name detector (Vosk).
- Boot receiver (optional; mic restriction note).
- Battery warnings.

**DoD:**
- Service survives screen off (testing).
- Wake triggers app + listening.
- Manual stop works.
- Battery impact documented.

### Phase 11 — USB + Bluetooth

Tasks:
- USB: `adb reverse` guide + 127.0.0.1 mode.
- BT: PAN mode guide + discovery.
- Connection mode switch.
- **Bluetooth PAN implementation:**
  - `BluetoothAdapter` + `BluetoothManager` for PAN profile
  - `BluetoothServerSocket` (laptop) / `BluetoothSocket` (phone) for RFCOMM fallback
  - PAN tethering: phone as PANU, laptop as NAP/GN
  - Auto-discovery via `BluetoothAdapter.startDiscovery()`
  - Pairing flow: phone shows PIN → laptop confirms
  - Connection manager: WiFi / USB / BT PAN mode switch in Settings

**DoD:**
- USB chat works with cable.
- BT PAN chat works after manual setup.
- Wrong mode → clear error.

### Phase 11B — Bluetooth Remote Control (Phone ↔ Laptop)

Tasks:
- **Phone side:**
  - `BluetoothRemoteService` — PAN server (NAP) + RFCOMM fallback
  - `BluetoothServerSocket` on laptop for incoming PAN connections
  - Phone discovers laptop via `BluetoothAdapter.getBondedDevices()`
  - Pairing confirmation dialog on both devices
  - PAN IP assignment (169.254.x.x link-local or DHCP)
  - Connection state: Disconnected / Connecting / Connected / Error
- **Laptop side:**
  - Bluetooth PAN client (connect to phone PAN)
  - RFCOMM client for legacy support
  - Settings: "Bluetooth" connection mode toggle
  - UI: Bluetooth device list + pair/connect buttons
  - Auto-reconnect on Bluetooth state change

**DoD:**
- Phone PAN + laptop PAN client connects
- Chat + remote control works over Bluetooth PAN
- RFCOMM fallback for older devices
- Auto-reconnect on Bluetooth on/off

### Phase 14 — Internet/WAN Remote Control

Tasks:
- **Relay Server (self-hosted):**
  - WebSocket relay: `wss://relay-host:port`
  - TLS termination (cert + key)
  - Connection routing: phone → relay → laptop
  - Token-based auth (reuse pairing tokens)
  - Rate limiting + connection limits
  - Health endpoint for monitoring
- **Phone side:**
  - `WanRemoteClient` — connects to relay via WebSocket
  - TLS cert pinning (embedded CA)
  - Auto-reconnect with exponential backoff
  - Settings: "Internet remote" toggle + relay URL input
  - Connection state indicator (LAN / WAN / Offline)
- **Laptop side:**
  - `WanRemoteServer` — accepts relay connections
  - WebSocket server with TLS (same cert as relay)
  - Settings: "Allow internet remote" toggle
  - UI: WAN connection status + relay URL config
- **Integration:**
  - Pairing token works for both LAN + WAN
  - Seamless handoff: LAN → WAN when WiFi lost
  - Phone Remote + Laptop Control both work over WAN

**DoD:**
- Relay server deployed + TLS working
- Phone connects to relay → laptop accepts
- Chat + Phone Remote + Laptop Control work over internet
- Auto-reconnect on network change
- Cert pinning prevents MITM

---

Tasks:
- All settings screens wired.
- Privacy export/delete.
- About + licenses.
- Full test pass.
- Release keystore + signed APK.

**DoD:**
- `assembleRelease` → signed APK.
- All unit + instrumented tests pass.
- Privacy export/delete works.

### Phase 13 — Phone remote (laptop controls phone)

Tasks:
- Phone: MediaProjection screen capture + JPEG encoding
- Phone: AccessibilityService input injection methods
- Phone: HTTP/WebSocket endpoints for remote session
- Phone: Foreground service with persistent notification
- Phone: File operations via SAF within allowed roots
- Laptop: PhoneRemotePage UI (screen view + input controls)
- Laptop: WebSocket client for screen stream + input send
- Integration: Pairing token auth, session confirm on phone
- Settings: "Allow laptop to control this phone" toggle

**DoD:**
- Phone grants MediaProjection → laptop sees live screen
- Laptop tap/swipe/type → executes on phone
- File browse/download/upload works
- Session confirm dialog on phone
- Stop session from laptop or phone notification
- Works over LAN (WiFi) + USB (adb reverse)
- No regression in existing phone/laptop control

---

**DoD:**
- `.\gradlew.bat test` green.
- `connectedDebugAndroidTest` green (core flows).
- Release APK installs.
- Manual checklist complete.

---

## 25. Testing plan

### Unit (JVM)
- `TokenVault` (instrumented — Keystore needs device).
- `PairingRepository` with MockWebServer.
- `ChatRepository` source selection.
- `ErrorMapper`.
- `PrivateNetworkInterceptor` (public host reject).
- Room DAO (in-memory, instrumented).
- Message mapper limits (24 / 12 000).

### UI tests (Compose)
- Onboarding → pairing.
- Bottom nav.
- Theme switch.
- Chat send with fake repo.
- Confirm dialog allow/cancel.

### Manual matrix

| Case | Check |
|---|---|
| Android 16 emulator | Install, pair, chat |
| Physical Android 16 | Same + permissions |
| Wi-Fi | Pair + chat + status |
| USB | adb reverse + chat |
| BT PAN | Manual setup + chat |
| Laptop offline | Phone model fallback |
| Phone model absent | Banner |
| Wrong PIN / expired QR | Errors |
| Accessibility restricted | Hint shown |
| Airplane mode | No cloud attempt; local only |
| App kill/restart | History + token persist |
| Revoke device | Token invalidated |

### Performance targets
- Cold start < 2 s.
- Chat screen scroll 60 fps.
- Streaming UI update ≤ 4 Hz DB writes.
- Memory < 250 MB (without phone model).
- Phone model load < 8 s.

---

## 26. Build & run commands

```powershell
cd "C:\Users\devar\Desktop\MAYA AI PROJECT\MOBILE APP"

# Debug APK
.\gradlew.bat assembleDebug

# Install
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r app\build\outputs\apk\debug\app-debug.apk

# Tests
.\gradlew.bat test
.\gradlew.bat connectedDebugAndroidTest

# Release (keystore.properties first)
.\gradlew.bat assembleRelease
```

Emulator (if needed):

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
& "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" "system-images;android-36;google_apis;x86_64"
& "$sdk\cmdline-tools\latest\bin\avdmanager.bat" create avd -n Maya_API36 -k "system-images;android-36;google_apis;x86_64"
& "$sdk\emulator\emulator.exe" -avd Maya_API36
```

Native deps (Phase 9):

```powershell
& "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" "ndk;27.2.12479018" "cmake;3.22.1"
```

---

## 27. Coding rules — vera AI coder-ku

1. English UI strings only in `strings.xml` — code-la hardcode pannaadhu.
2. Compose only — XML layouts illa.
3. StateFlow + immutable UI state; `collectAsStateWithLifecycle`.
4. No `GlobalScope`; use `viewModelScope` / `lifecycleScope`.
5. Manual DI (`AppContainer`) — Hilt/Koin v1-la venam.
6. Repository layer mela network call illa (ViewModel-la OkHttp illa).
7. Room query main thread-la illa.
8. Token / personal data log pannaadhu.
9. API contract change panna → `docs\API-CONTRACT.md` update pannu (additive mattum).
10. New permission add panna → Privacy screen + rationale update pannu.
11. Dark + light rendu-lum test pannu.
12. Screen reader (TalkBack) basic check.
13. `TODO` code merge pannaadhu — feature flag / phase marker use pannu.
14. Copy persona files from `MAYA AI\persona\` → app assets; editing rendu-lum sync pannu.

---

## 28. Risks / known limitations

| Risk | Impact | Mitigation |
|---|---|---|
| Android 16 min | Few real devices | Emulator + own phone |
| Sideload accessibility restricted | Screen control blocked | In-app guide + settings deep link |
| Background mic restrictions | Wake unreliable | Foreground service + user opt-in |
| Bluetooth transport | No standard HTTP over BT | Use BT PAN (manual); RFCOMM v2 |
| llama.cpp build complexity | Phase 9 delay | Laptop-first MVP; Phase 9 independent |
| Piper AAR availability | Tamil TTS missing | Android TTS fallback |
| tamil-lm-2b RAM | Low-end phones | 6 GB recommendation, unload on trim |
| Cleartext HTTP LAN | Sniffing risk | Trusted LAN only; TLS v2 |
| QUERY_ALL_PACKAGES | Play policy (sideload only) | Not for Play Store |
| Android 16 SMS permissions | Limited default-SMS role | Sideload + runtime grant |

---

## 29. Handoff checklist (before "done")

- [ ] All 12 phases DoD pass.
- [ ] `assembleDebug` + `assembleRelease` success.
- [ ] Unit + UI tests green.
- [ ] Pairing (PIN + QR) with real laptop.
- [ ] Auto-connect + revoke tested.
- [ ] Chat streaming + cancel + retry.
- [ ] Voice round trip.
- [ ] Phone control features with confirmations.
- [ ] Laptop control confirm flow.
- [ ] Monitoring accurate.
- [ ] On-device reply offline.
- [ ] Wake triggers tested.
- [ ] USB + BT PAN documented and tested.
- [ ] No cloud / analytics code (`grep -r "http" ` review).
- [ ] `docs\API-CONTRACT.md` matches implementation.
- [ ] Release signed + version noted.

---

## 30. Open questions (non-blocking)

1. App icon final design (placeholder now).
2. Piper Tamil voice name (pick after listening tests).
3. "Maya" name detection model size vs battery trade-off.
4. Whether phone app should also show laptop notifications (v2).
5. Play Store distribution? (Currently sideload only.)

---

**Next file to read:** `LAPTOP\windows\PLAN.md` (server side) + `docs\API-CONTRACT.md`.
**Build command:** `.\gradlew.bat assembleDebug`
