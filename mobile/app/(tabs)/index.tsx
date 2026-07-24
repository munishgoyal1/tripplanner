import { Pressable, StyleSheet, Text, View } from 'react-native';

import { EmptyState, Screen } from '@/components/screen';
import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

export default function HomeScreen() {
  const { trips, startNewTrip, switchTrip } = useTrip();
  return (
    <Screen
      title="My trips"
      subtitle="Saved plans follow you across devices"
      action={<Pressable onPress={() => void startNewTrip()} style={styles.newButton}><Text style={styles.newButtonText}>New</Text></Pressable>}
    >
      {trips.length === 0 ? <EmptyState>Start in Assistant and describe where you want to go.</EmptyState> : trips.map((trip) => (
        <Pressable
          accessibilityRole="button"
          key={trip.trip_id}
          onPress={() => void switchTrip(trip.trip_id)}
          style={[styles.trip, trip.is_active && styles.tripActive]}
        >
          <View style={styles.tripTop}>
            <Text style={styles.destination}>{trip.destination}</Text>
            <Text style={[styles.status, trip.is_active && styles.statusActive]}>{trip.is_active ? 'Active' : trip.status}</Text>
          </View>
          <Text style={styles.dates}>{trip.departure_date || 'Dates open'}{trip.return_date ? ` to ${trip.return_date}` : ''}</Text>
          <Text style={styles.meta}>{trip.counts.hotels} stays · {trip.counts.activities} places · {trip.currency} {trip.total_cost || 0}</Text>
        </Pressable>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  newButton: { backgroundColor: palette.brand, borderRadius: 8, paddingHorizontal: 17, paddingVertical: 10 },
  newButtonText: { color: '#fff', fontWeight: '700' },
  trip: { backgroundColor: palette.surface, borderColor: palette.line, borderWidth: 1, borderRadius: 8, padding: 17, marginBottom: 12, gap: 7 },
  tripActive: { borderColor: palette.brand, borderWidth: 2 },
  tripTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  destination: { flex: 1, color: palette.ink, fontFamily: 'Georgia', fontSize: 21, fontWeight: '700' },
  status: { color: palette.muted, backgroundColor: palette.canvas, borderRadius: 10, paddingHorizontal: 9, paddingVertical: 4, fontSize: 12, textTransform: 'capitalize' },
  statusActive: { color: palette.brand, backgroundColor: palette.brandSoft },
  dates: { color: palette.ink, fontSize: 14 },
  meta: { color: palette.muted, fontSize: 13 },
});
