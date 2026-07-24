import type { PropsWithChildren, ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

interface ScreenProps extends PropsWithChildren {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  scroll?: boolean;
}

export function Screen({ title, subtitle, action, scroll = true, children }: ScreenProps) {
  const { error, loading, refresh } = useTrip();
  const content = (
    <>
      <View style={styles.header}>
        <View style={styles.heading}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        {action}
      </View>
      {error ? (
        <Pressable accessibilityRole="button" onPress={() => void refresh()} style={styles.error}>
          <Text style={styles.errorText}>{error} Tap to retry.</Text>
        </Pressable>
      ) : null}
      {loading && !children ? <ActivityIndicator color={palette.brand} style={styles.loader} /> : children}
    </>
  );

  return (
    <SafeAreaView edges={['top']} style={styles.safe}>
      {scroll ? <ScrollView contentContainerStyle={styles.content}>{content}</ScrollView> : <View style={styles.content}>{content}</View>}
    </SafeAreaView>
  );
}

export function EmptyState({ children }: PropsWithChildren) {
  return <Text style={styles.empty}>{children}</Text>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.canvas },
  content: { flexGrow: 1, paddingHorizontal: 18, paddingBottom: 28 },
  header: { minHeight: 82, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 16 },
  heading: { flex: 1, gap: 2 },
  title: { color: palette.ink, fontFamily: 'Georgia', fontSize: 30, fontWeight: '700' },
  subtitle: { color: palette.muted, fontSize: 13 },
  error: { backgroundColor: '#FFF7ED', borderColor: '#FED7AA', borderWidth: 1, borderRadius: 8, padding: 12, marginBottom: 12 },
  errorText: { color: palette.warning, fontSize: 13, lineHeight: 18 },
  loader: { marginTop: 48 },
  empty: { color: palette.muted, fontSize: 15, lineHeight: 22, textAlign: 'center', marginTop: 80, paddingHorizontal: 28 },
});