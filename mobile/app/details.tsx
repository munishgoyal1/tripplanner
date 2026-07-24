import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

export default function DetailsScreen() {
  const params = useLocalSearchParams<{ kind: string; name: string; day?: string; stop?: string }>();
  const router = useRouter();
  const { addPlace, removePlace, view } = useTrip();
  const item = view?.items.find((candidate) => candidate.name.toLowerCase() === params.name?.toLowerCase());
  const kind = params.kind || item?.kind || 'attraction';
  const occurrence = params.day !== undefined && params.stop !== undefined
    ? { day: Number(params.day), stop: Number(params.stop), all_occurrences: false }
    : undefined;

  return (
    <SafeAreaView edges={['bottom']} style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        {item?.photos[0] ? <Image contentFit="cover" source={item.photos[0]} style={styles.photo} /> : <View style={styles.photoFallback}><Text style={styles.photoLetter}>{params.name?.slice(0, 1)}</Text></View>}
        <Text style={styles.kind}>{kind}</Text>
        <Text style={styles.name}>{params.name}</Text>
        {item?.rating ? <Text style={styles.rating}>★ {item.rating.toFixed(1)} · {item.review_count || 0} reviews</Text> : null}
        {item?.address ? <Text style={styles.address}>{item.address}</Text> : null}
        {item?.summary ? <Text style={styles.summary}>{item.summary}</Text> : null}
        {item?.occurrences?.length ? <View style={styles.occurrences}><Text style={styles.sectionTitle}>In your itinerary</Text>{item.occurrences.map((row) => <Text key={`${row.day}-${row.stop}`} style={styles.occurrence}>Day {row.day}{row.time ? ` · ${row.time}` : ''}</Text>)}</View> : null}
        <Pressable
          onPress={async () => {
            if (item?.selected) await removePlace(kind, params.name, occurrence);
            else await addPlace(kind, params.name);
            router.back();
          }}
          style={[styles.primary, item?.selected && styles.remove]}
        >
          <Text style={styles.primaryText}>{item?.selected ? (occurrence ? 'Remove this stop' : 'Remove from trip') : 'Add to trip'}</Text>
        </Pressable>
        {item?.selected && item.occurrences.length > 1 && occurrence ? (
          <Pressable onPress={async () => { await removePlace(kind, params.name, { all_occurrences: true }); router.back(); }} style={styles.secondary}><Text style={styles.secondaryText}>Remove everywhere</Text></Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.surface },
  content: { padding: 18, paddingBottom: 38 },
  photo: { width: '100%', aspectRatio: 1.6, borderRadius: 8, marginBottom: 20, backgroundColor: palette.canvas },
  photoFallback: { width: '100%', aspectRatio: 1.8, borderRadius: 8, marginBottom: 20, backgroundColor: palette.accentSoft, alignItems: 'center', justifyContent: 'center' },
  photoLetter: { color: palette.accent, fontFamily: 'Georgia', fontSize: 58, fontWeight: '700' },
  kind: { color: palette.brand, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  name: { color: palette.ink, fontFamily: 'Georgia', fontSize: 29, lineHeight: 35, fontWeight: '700', marginTop: 4 },
  rating: { color: palette.ink, fontSize: 14, fontWeight: '600', marginTop: 10 },
  address: { color: palette.muted, fontSize: 13, lineHeight: 19, marginTop: 7 },
  summary: { color: palette.ink, fontSize: 15, lineHeight: 23, marginTop: 18 },
  occurrences: { borderTopColor: palette.line, borderTopWidth: 1, marginTop: 22, paddingTop: 18, gap: 7 },
  sectionTitle: { color: palette.ink, fontSize: 15, fontWeight: '700' },
  occurrence: { color: palette.muted, fontSize: 13 },
  primary: { backgroundColor: palette.brand, borderRadius: 8, alignItems: 'center', paddingVertical: 14, marginTop: 25 },
  remove: { backgroundColor: palette.ink },
  primaryText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  secondary: { alignItems: 'center', paddingVertical: 14, marginTop: 8 },
  secondaryText: { color: palette.brand, fontSize: 14, fontWeight: '700' },
});