import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Screen } from '@/components/screen';
import { palette } from '@/constants/tripplanner-theme';
import {
  apiBaseUrl,
  fetchMobilePreferences,
  saveMobilePreferences,
  type MobilePreferences,
} from '@/lib/tripplanner';
import { LatestRequestGate } from '@/lib/latest-request';
import { useTrip } from '@/providers/trip-provider';

const EMPTY: MobilePreferences = {
  display_name: '',
  home_city: '',
  home_country: '',
  trip_style: '',
  budget_level: '',
  about_me: '',
};

const FIELDS = ['display_name', 'home_city', 'home_country', 'trip_style', 'budget_level'] as const;

export default function AccountScreen() {
  const { account, refresh, signIn, signOut } = useTrip();
  const [preferences, setPreferences] = useState<MobilePreferences>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [dirtyFields, setDirtyFields] = useState<Set<keyof MobilePreferences>>(new Set());
  const preferenceRequestGate = useRef(new LatestRequestGate());

  useEffect(() => {
    const requestGate = preferenceRequestGate.current;
    const request = requestGate.start();
    setMessage('');
    void fetchMobilePreferences()
      .then((next) => {
        if (!request.isCurrent()) return;
        setPreferences(next);
        setDirtyFields(new Set());
      })
      .catch((error) => {
        if (request.isCurrent()) {
          setMessage(error instanceof Error ? error.message : 'Could not load preferences.');
        }
      });
    return () => requestGate.abort();
  }, [account]);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      const updates: Partial<MobilePreferences> = {};
      for (const key of dirtyFields) {
        Object.assign(updates, { [key]: preferences[key] });
      }
      await saveMobilePreferences(updates);
      setDirtyFields(new Set());
      setMessage('Preferences saved.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save preferences.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen title="Account" subtitle={account ? account.email : 'Local mobile profile'}>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{account ? account.display_name || 'Google account' : 'Keep trips in sync'}</Text>
        <Text style={styles.copy}>
          {account
            ? 'Your web and mobile trips use the same account.'
            : 'Sign in with Google to load trips and chat history from the web app.'}
        </Text>
        <Pressable onPress={() => void (account ? signOut() : signIn())} style={account ? styles.secondaryButton : styles.primaryButton}>
          <Text style={account ? styles.secondaryText : styles.primaryText}>{account ? 'Sign out' : 'Sign in with Google'}</Text>
        </Pressable>
      </View>

      <View style={styles.section}>
        <View style={styles.row}>
          <Text style={styles.sectionTitle}>Travel preferences</Text>
          <Pressable onPress={() => void refresh()}><Text style={styles.link}>Refresh data</Text></Pressable>
        </View>
        {FIELDS.map((key) => (
          <View key={key} style={styles.field}>
            <Text style={styles.label}>{key.replaceAll('_', ' ')}</Text>
            <TextInput
              editable={!saving}
              value={preferences[key]}
              onChangeText={(value) => {
                setDirtyFields((current) => new Set(current).add(key));
                setPreferences((current) => ({ ...current, [key]: value }));
              }}
              style={styles.input}
            />
          </View>
        ))}
        <View style={styles.field}>
          <Text style={styles.label}>about me</Text>
          <TextInput
            editable={!saving}
            multiline
            value={preferences.about_me}
            onChangeText={(value) => {
              setDirtyFields((current) => new Set(current).add('about_me'));
              setPreferences((current) => ({ ...current, about_me: value }));
            }}
            style={[styles.input, styles.multiline]}
          />
        </View>
        <Pressable disabled={saving || dirtyFields.size === 0} onPress={() => void save()} style={styles.primaryButton}>
          <Text style={styles.primaryText}>{saving ? 'Saving…' : 'Save preferences'}</Text>
        </Pressable>
        {message ? <Text style={styles.message}>{message}</Text> : null}
      </View>

      <View style={styles.status}>
        <Text style={styles.label}>API</Text>
        <Text selectable style={styles.api}>{apiBaseUrl}</Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { backgroundColor: palette.surface, borderColor: palette.line, borderWidth: 1, borderRadius: 8, padding: 16, marginBottom: 14, gap: 12 },
  sectionTitle: { color: palette.ink, fontSize: 17, fontWeight: '700' },
  copy: { color: palette.muted, fontSize: 13, lineHeight: 19 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  link: { color: palette.brand, fontSize: 13, fontWeight: '600' },
  field: { gap: 5 },
  label: { color: palette.muted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  input: { minHeight: 44, borderColor: palette.line, borderWidth: 1, borderRadius: 8, backgroundColor: palette.canvas, color: palette.ink, paddingHorizontal: 12, paddingVertical: 10 },
  multiline: { minHeight: 92, textAlignVertical: 'top' },
  primaryButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 8, backgroundColor: palette.brand, paddingHorizontal: 16 },
  primaryText: { color: '#fff', fontWeight: '700' },
  secondaryButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 8, borderColor: palette.line, borderWidth: 1, paddingHorizontal: 16 },
  secondaryText: { color: palette.ink, fontWeight: '700' },
  message: { color: palette.accent, fontSize: 12 },
  status: { padding: 12, gap: 4 },
  api: { color: palette.muted, fontSize: 11 },
});