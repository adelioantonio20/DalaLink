import React, { useEffect, useRef } from 'react';
import L from 'leaflet';

export interface MapMarkerItem {
  id: string;
  lat: number;
  lng: number;
  label: string;
  sublabel?: string;
  kind: 'pickup' | 'dropoff' | 'vehicle_available' | 'vehicle_busy' | 'stop' | 'request';
}

export interface DemandCircleItem {
  zone: string;
  lat: number;
  lng: number;
  level: 'ELEVADA' | 'MODERADA' | 'BAIXA';
  activeRequests: number;
  availableVehicles: number;
}

interface LuandaMapProps {
  heightClass?: string;
  center?: [number, number];
  zoom?: number;
  markers?: MapMarkerItem[];
  routeLine?: [number, number][];
  demandCircles?: DemandCircleItem[];
  onMapClick?: (lat: number, lng: number) => void;
}

const MARKER_STYLES: Record<MapMarkerItem['kind'], { bg: string; glyph: string; size: number }> = {
  pickup: { bg: '#0D7C5F', glyph: 'P', size: 32 },
  dropoff: { bg: '#D97706', glyph: 'D', size: 32 },
  vehicle_available: { bg: '#059669', glyph: 'T', size: 30 },
  vehicle_busy: { bg: '#0F172A', glyph: 'V', size: 32 },
  stop: { bg: '#475569', glyph: '•', size: 18 },
  request: { bg: '#DC2626', glyph: '!', size: 28 },
};

export const LuandaMap: React.FC<LuandaMapProps> = ({
  heightClass = 'h-80',
  center = [-8.868, 13.224],
  zoom = 13,
  markers = [],
  routeLine = [],
  demandCircles = [],
  onMapClick,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center,
      zoom,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap • Luanda',
      maxZoom: 18,
    }).addTo(map);

    const group = L.layerGroup().addTo(map);
    mapRef.current = map;
    layerGroupRef.current = group;

    return () => {
      map.remove();
      mapRef.current = null;
      layerGroupRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e: L.LeafletMouseEvent) => {
      if (onMapClick) {
        onMapClick(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6)));
      }
    };
    map.on('click', handler);
    return () => {
      map.off('click', handler);
    };
  }, [onMapClick]);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerGroupRef.current;
    if (!map || !group) return;

    group.clearLayers();

    // Demand pressure heat circles (Admin / Intelligence view)
    demandCircles.forEach((dc) => {
      const color =
        dc.level === 'ELEVADA' ? '#DC2626' : dc.level === 'MODERADA' ? '#D97706' : '#0D7C5F';
      const circle = L.circle([dc.lat, dc.lng], {
        radius: dc.level === 'ELEVADA' ? 1200 : dc.level === 'MODERADA' ? 900 : 650,
        color,
        fillColor: color,
        fillOpacity: dc.level === 'ELEVADA' ? 0.25 : 0.14,
        weight: 1.5,
      });
      circle.bindPopup(
        `<strong>${dc.zone}</strong><br/>Pressão: ${dc.level}<br/>Procura ativa: ${dc.activeRequests} | Veículos livres: ${dc.availableVehicles}`
      );
      circle.addTo(group);
    });

    // Route polyline
    if (routeLine.length >= 2) {
      L.polyline(routeLine, {
        color: '#0D7C5F',
        weight: 4,
        opacity: 0.85,
        dashArray: '8 6',
      }).addTo(group);
    }

    // Markers
    const boundsPoints: L.LatLngExpression[] = [];
    markers.forEach((m) => {
      const style = MARKER_STYLES[m.kind];
      const icon = L.divIcon({
        className: 'custom-dalalink-pin',
        html: `<div class="dalalink-marker" style="width:${style.size}px;height:${style.size}px;background:${style.bg};color:#fff;font-size:${style.size > 22 ? 12 : 10}px;">${style.glyph}</div>`,
        iconSize: [style.size, style.size],
        iconAnchor: [style.size / 2, style.size / 2],
      });
      const marker = L.marker([m.lat, m.lng], { icon });
      marker.bindPopup(
        `<div style="min-width:140px"><strong>${m.label}</strong>${
          m.sublabel ? `<div style="font-size:12px;color:#475569;margin-top:2px">${m.sublabel}</div>` : ''
        }</div>`
      );
      marker.addTo(group);
      if (m.kind !== 'stop') {
        boundsPoints.push([m.lat, m.lng]);
      }
    });

    if (boundsPoints.length >= 2) {
      map.fitBounds(L.latLngBounds(boundsPoints), { padding: [36, 36], maxZoom: 14 });
    } else if (boundsPoints.length === 1) {
      map.setView(boundsPoints[0], 14);
    }
  }, [markers, routeLine, demandCircles]);

  return (
    <div className={`relative w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 ${heightClass}`}>
      <div ref={containerRef} className="h-full w-full" />
      <div className="pointer-events-none absolute bottom-2 left-2 z-[400] rounded-lg bg-white/90 px-2.5 py-1 text-[11px] font-medium text-slate-700 shadow-sm backdrop-blur-sm">
        Luanda, Angola • OpenStreetMap
      </div>
    </div>
  );
};
