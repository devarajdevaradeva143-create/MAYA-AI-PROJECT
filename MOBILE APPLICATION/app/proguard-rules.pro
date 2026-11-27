# Keep default rules; release minify is disabled for v1.
-dontwarn org.bouncycastle.**

# WebRTC is accessed via native/JNI reflection; keep the whole public API.
-keep class org.webrtc.** { *; }
-keepclassmembers class org.webrtc.** { native <methods>; }
-dontwarn org.webrtc.**

# Manual signaling codec used across processes/layers.
-keep class com.devaraj.maya.p2p.** { *; }
