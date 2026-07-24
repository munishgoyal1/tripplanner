import { useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

export default function AssistantScreen() {
  const { messages, sendMessage, sending, view } = useTrip();
  const [draft, setDraft] = useState('');
  const submit = () => {
    const message = draft.trim();
    if (!message) return;
    setDraft('');
    void sendMessage(message);
  };

  return (
    <SafeAreaView edges={['top']} style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={82} style={styles.keyboard}>
        <View style={styles.header}><Text style={styles.title}>Assistant</Text><Text style={styles.subtitle}>{view?.destination || 'Plan a complete trip'}</Text></View>
        <FlatList
          data={messages}
          keyExtractor={(_, index) => String(index)}
          contentContainerStyle={styles.messages}
          ListEmptyComponent={<Text style={styles.empty}>Tell me a destination, dates, travelers, and what matters most.</Text>}
          renderItem={({ item }) => <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}><Text style={[styles.message, item.role === 'user' && styles.userMessage]}>{item.text}</Text></View>}
        />
        {sending ? <View style={styles.thinking}><ActivityIndicator size="small" color={palette.accent} /><Text style={styles.thinkingText}>Working on your trip…</Text></View> : null}
        <View style={styles.composer}>
          <TextInput
            accessibilityLabel="Message the trip assistant"
            multiline
            onChangeText={setDraft}
            placeholder="Ask about your trip"
            placeholderTextColor={palette.muted}
            style={styles.input}
            value={draft}
          />
          <Pressable accessibilityLabel="Send message" disabled={!draft.trim() || sending} onPress={submit} style={[styles.send, (!draft.trim() || sending) && styles.sendDisabled]}><Text style={styles.sendText}>↑</Text></Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.canvas },
  keyboard: { flex: 1 },
  header: { paddingHorizontal: 18, paddingVertical: 14, borderBottomColor: palette.line, borderBottomWidth: 1 },
  title: { color: palette.ink, fontFamily: 'Georgia', fontSize: 28, fontWeight: '700' },
  subtitle: { color: palette.muted, fontSize: 12, marginTop: 2 },
  messages: { flexGrow: 1, padding: 16, gap: 12, justifyContent: 'flex-end' },
  empty: { color: palette.muted, textAlign: 'center', lineHeight: 22, paddingHorizontal: 30, marginBottom: 80 },
  bubble: { maxWidth: '88%', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 11 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: palette.brand },
  assistantBubble: { alignSelf: 'flex-start', backgroundColor: palette.surface, borderColor: palette.line, borderWidth: 1 },
  message: { color: palette.ink, fontSize: 15, lineHeight: 21 },
  userMessage: { color: '#fff' },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 18, paddingBottom: 8 },
  thinkingText: { color: palette.muted, fontSize: 12 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 9, padding: 12, borderTopColor: palette.line, borderTopWidth: 1, backgroundColor: palette.surface },
  input: { flex: 1, maxHeight: 110, minHeight: 46, backgroundColor: palette.canvas, borderColor: palette.line, borderWidth: 1, borderRadius: 8, paddingHorizontal: 13, paddingVertical: 12, color: palette.ink, fontSize: 15 },
  send: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.brand },
  sendDisabled: { opacity: 0.4 },
  sendText: { color: '#fff', fontSize: 25, fontWeight: '700', marginTop: -3 },
});