import { App } from '@capacitor/app';
import { Capacitor, registerPlugin } from '@capacitor/core';

window.ChaosNativeApp = App;
if (Capacitor.isNativePlatform()) window.ChaosGoogleSignIn = registerPlugin('ChaosGoogleSignIn');
