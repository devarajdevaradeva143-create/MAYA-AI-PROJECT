# Release builds use R8 + resource shrinking; debug stays unminified.
-dontwarn org.bouncycastle.**

# WebRTC (com.infobip:google-webrtc) exposes org.webrtc classes to native/JNI;
# the AAR contains only org.webrtc classes (no com.infobip.* bytecode).
-keep class org.webrtc.** { *; }
-keepclassmembers class org.webrtc.** { native <methods>; }
-dontwarn org.webrtc.**

# Manual signaling codec used across processes/layers.
-keep class com.devaraj.maya.p2p.** { *; }

# JNI bridge: native-lib.cpp resolves NativeLlama by class/method name and
# invokes the streaming callback's Function1.invoke reflectively.
-keep class com.devaraj.maya.data.model.NativeLlama { *; }
-keepclasseswithmembernames class * { native <methods>; }
