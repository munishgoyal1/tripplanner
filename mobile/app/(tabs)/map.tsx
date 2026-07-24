import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

import { EmptyState, Screen } from '@/components/screen';
import { palette } from '@/constants/tripplanner-theme';
import { useTrip } from '@/providers/trip-provider';

export default function TripMapScreen() {
  const { map } = useTrip();
  if (!map?.center) return <Screen title="Map"><EmptyState>{map?.empty_message || 'Map places will appear after planning begins.'}</EmptyState></Screen>;

  const pinsById = new Map(map.pins.map((pin) => [pin.id, pin]));
  return (
    <Screen title={map.destination || 'Map'} subtitle={`${map.pins.length} places across ${map.days.length} days`} scroll={false}>
      <MapView
        style={styles.map}
        initialRegion={{ latitude: map.center.lat, longitude: map.center.lng, latitudeDelta: 0.12, longitudeDelta: 0.12 }}
      >
        {map.days.map((day) => (
          <Polyline
            key={day.day}
            coordinates={day.pin_ids.map((id) => pinsById.get(id)).filter((pin) => Boolean(pin)).map((pin) => ({ latitude: pin!.lat, longitude: pin!.lng }))}
            strokeColor={day.color || palette.brand}
            strokeWidth={3}
          />
        ))}
        {map.pins.map((pin) => (
          <Marker key={pin.id} coordinate={{ latitude: pin.lat, longitude: pin.lng }} pinColor={pin.selected ? palette.brand : palette.accent}>
            <Link href={{ pathname: '/details', params: { kind: pin.kind, name: pin.name } }} asChild>
              <View style={[styles.marker, pin.selected && styles.markerSelected]}><Text style={styles.markerText}>{pin.day || '·'}</Text></View>
            </Link>
          </Marker>
        ))}
      </MapView>
      <View style={styles.legend}><Text style={styles.legendText}>Tap a numbered place for details</Text></View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  map: { flex: 1, marginHorizontal: -18 },
  marker: { width: 30, height: 30, borderRadius: 15, backgroundColor: palette.accent, borderWidth: 3, borderColor: '#fff', alignItems: 'center', justifyContent: 'center' },
  markerSelected: { backgroundColor: palette.brand },
  markerText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  legend: { position: 'absolute', left: 16, right: 16, bottom: 16, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 8, paddingVertical: 10, alignItems: 'center' },
  legendText: { color: palette.ink, fontSize: 12, fontWeight: '600' },
});