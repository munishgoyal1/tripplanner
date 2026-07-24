import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { EmptyState, Screen } from '@/components/screen';
import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

export default function PlanScreen() {
  const { itinerary, setBooked, view } = useTrip();
  return (
    <Screen title={view?.destination || 'Your plan'} subtitle={view?.overview?.total_cost_display || 'Day by day'}>
      {!itinerary?.has_itinerary ? <EmptyState>Your itinerary will appear as the Assistant builds it.</EmptyState> : itinerary.days.map((day) => (
        <View key={day.day} style={styles.day}>
          <View style={styles.dayHeader}>
            <View style={[styles.dayNumber, { backgroundColor: day.color || palette.accent }]}><Text style={styles.dayNumberText}>{day.day}</Text></View>
            <View style={styles.dayHeading}>
              <Text style={styles.dayTitle}>{day.title}</Text>
              <Text style={styles.dayMeta}>{day.stops.length} stops{day.route ? ` · ${day.route.distance_display} · ${day.route.duration_display}` : ''}</Text>
            </View>
          </View>
          {day.stops.map((stop, stopIndex) => (
            <Link key={`${day.day}-${stopIndex}-${stop.name}`} href={{ pathname: '/details', params: { kind: stop.kind, name: stop.name, day: day.day, stop: stopIndex } }} asChild>
              <Pressable style={styles.stop}>
                <View style={styles.timeRail}><Text style={styles.time}>{stop.time || 'Anytime'}</Text><View style={styles.rail} /></View>
                <View style={styles.stopBody}>
                  <Text style={styles.stopName}>{stop.name}</Text>
                  <Text numberOfLines={2} style={styles.note}>{stop.note || stop.kind}</Text>
                </View>
                <Pressable
                  accessibilityLabel={`${stop.booked ? 'Mark unbooked' : 'Mark booked'} ${stop.name}`}
                  hitSlop={10}
                  onPress={() => void setBooked(day.day, stop.name, !stop.booked)}
                  style={[styles.booked, stop.booked && styles.bookedActive]}
                >
                  <Text style={[styles.bookedText, stop.booked && styles.bookedTextActive]}>{stop.booked ? 'Booked' : 'Open'}</Text>
                </Pressable>
              </Pressable>
            </Link>
          ))}
        </View>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  day: { backgroundColor: palette.surface, borderColor: palette.line, borderWidth: 1, borderRadius: 8, marginBottom: 16, overflow: 'hidden' },
  dayHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 15, backgroundColor: '#FCFCFD' },
  dayNumber: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  dayNumberText: { color: '#fff', fontWeight: '800' },
  dayHeading: { flex: 1, gap: 3 },
  dayTitle: { color: palette.ink, fontSize: 17, fontWeight: '700' },
  dayMeta: { color: palette.muted, fontSize: 12 },
  stop: { minHeight: 74, flexDirection: 'row', gap: 10, alignItems: 'stretch', borderTopColor: palette.line, borderTopWidth: 1, paddingHorizontal: 14, paddingTop: 12 },
  timeRail: { width: 55, alignItems: 'center', gap: 5 },
  time: { color: palette.accent, fontSize: 11, fontWeight: '700' },
  rail: { width: 2, flex: 1, backgroundColor: '#CCFBF1' },
  stopBody: { flex: 1, paddingBottom: 12, gap: 4 },
  stopName: { color: palette.ink, fontSize: 15, fontWeight: '700' },
  note: { color: palette.muted, fontSize: 12, lineHeight: 17, textTransform: 'capitalize' },
  booked: { alignSelf: 'flex-start', borderColor: palette.line, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 },
  bookedActive: { backgroundColor: palette.accentSoft, borderColor: '#99F6E4' },
  bookedText: { color: palette.muted, fontSize: 11, fontWeight: '700' },
  bookedTextActive: { color: palette.accent },
});