import { DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { TripProvider } from '@/providers/trip-provider';
import { palette } from '@/constants/tripplanner-theme';

export const unstable_settings = {
  anchor: '(tabs)',
};

export default function RootLayout() {
  return (
    <TripProvider>
      <ThemeProvider value={{ ...DefaultTheme, colors: { ...DefaultTheme.colors, background: palette.canvas, primary: palette.brand } }}>
        <Stack>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="details" options={{ presentation: 'formSheet', title: 'Place details', sheetGrabberVisible: true }} />
        </Stack>
        <StatusBar style="dark" />
      </ThemeProvider>
    </TripProvider>
  );
}
