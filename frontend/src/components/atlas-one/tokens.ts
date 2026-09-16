/**
 * Atlas One design tokens
 * Source: C:\Users\ecamp\Devs\Atlas Brain\AtlasONE\ATLAS ONE\system.jsx (lines 11-155)
 */

export const ATLAS_FONT = "'IBM Plex Sans', system-ui, sans-serif";
export const ATLAS_MONO = "'IBM Plex Mono', ui-monospace, monospace";
export const ATLAS_SERIF = "'IBM Plex Serif', Georgia, serif";

// Neutral light-mode canvas (warm off-white)
export const N = {
  canvas: '#F6F4EF',     // app outer bg (warm)
  page:   '#FBFAF6',     // page bg inside main area
  card:   '#FFFFFF',     // card surface
  ink:    '#0B0B0B',     // primary text
  body:   '#2A2A28',     // body text
  muted:  '#6B6B66',     // secondary
  faint:  '#9C9B95',     // tertiary
  line:   '#E8E5DD',     // hairline
  line2:  '#D9D5CB',     // stronger hairline
  chip:   '#F2EFE7',     // chip / subtle fill
  inkDark: '#0E0E10',
  inkSoft: '#19191C',
} as const;

export interface PresetSidebar {
  bg: string;
  fg: string;
  mute: string;
  activeBg: string;
  accent: string;
}

export interface PresetConfig {
  name: string;
  tagline: string;
  description: string;
  accent: string;
  accent2: string;
  accentSoft: string;
  accentInk: string;
  tint: string;
  sidebar: PresetSidebar;
}

export const PRESETS = {
  pos: {
    name: 'Atlas POS',
    tagline: 'Entrada universal',
    description: 'Vender, cobrar y controlar caja desde el día uno.',
    accent: '#2563EB',
    accent2: '#60A5FA',
    accentSoft: '#EEF3FE',
    accentInk: '#1E3A8A',
    tint: '#EDF2FB',
    sidebar: { bg: '#0F1726', fg: '#E6EEFB', mute: '#7C8AA8', activeBg: '#1A2740', accent: '#60A5FA' },
  },
  retail: {
    name: 'Atlas One Retail',
    tagline: 'Inventario que cuadra',
    description: 'Productos, SKU, stock y mostrador para tiendas con inventario exigente.',
    accent: '#0B3A8F',
    accent2: '#06B6D4',
    accentSoft: '#E6F0FB',
    accentInk: '#082A6B',
    tint: '#E8F1FB',
    sidebar: { bg: '#0A1426', fg: '#DCE7F6', mute: '#6E80A0', activeBg: '#102348', accent: '#22D3EE' },
  },
  barber: {
    name: 'Atlas One Barber',
    tagline: 'Silla, navaja y agenda',
    description: 'Agenda por barbero, servicios, comisiones y clientes frecuentes.',
    accent: '#0F766E',
    accent2: '#22D3B8',
    accentSoft: '#EBF2F1',
    accentInk: '#064E47',
    tint: '#EEF1F0',
    sidebar: { bg: '#0B0B0C', fg: '#E8E6E2', mute: '#7A7872', activeBg: '#171716', accent: '#22D3B8' },
  },
  restaurant: {
    name: 'Atlas One Restaurant',
    tagline: 'Salón, comanda y cocina',
    description: 'Plano de mesas, comandas, KDS y operación por turno.',
    accent: '#E2531B',
    accent2: '#F59E0B',
    accentSoft: '#FBEEE5',
    accentInk: '#8A2C0A',
    tint: '#F8EEE6',
    sidebar: { bg: '#1A0F0A', fg: '#F4E9DF', mute: '#8C7E72', activeBg: '#2A1A11', accent: '#F59E0B' },
  },
  beauty_wellness: {
    name: 'Atlas One Beauty',
    tagline: 'Salón, agenda y membresías',
    description: 'Estéticas, uñas, spa y bienestar con alta recurrencia.',
    accent: '#B16E78',
    accent2: '#D9B58C',
    accentSoft: '#F4E8E8',
    accentInk: '#6E3F47',
    tint: '#F6ECE8',
    sidebar: { bg: '#1C1212', fg: '#F2E7E5', mute: '#9D817F', activeBg: '#2A1B1B', accent: '#D9B58C' },
  },
  health: {
    name: 'Atlas One Health',
    tagline: 'Agenda y expediente clínico',
    description: 'Consultorios, citas, pacientes y seguimiento clínico.',
    accent: '#0E9F9C',
    accent2: '#7DD3FC',
    accentSoft: '#E1F5F4',
    accentInk: '#075E5C',
    tint: '#E7F3F2',
    sidebar: { bg: '#0E1F23', fg: '#E1F5F4', mute: '#6E8C8E', activeBg: '#16323A', accent: '#5EEAD4' },
  },
  cafe: {
    name: 'Atlas One Café',
    tagline: 'Barra rápida, recetas, insumos',
    description: 'Cafeterías, panaderías y barras con alta demanda.',
    accent: '#8B4A2B',
    accent2: '#D9A668',
    accentSoft: '#F4E8DB',
    accentInk: '#5A2F18',
    tint: '#F1E5D2',
    sidebar: { bg: '#2A1810', fg: '#F4E8DB', mute: '#A48667', activeBg: '#3D2418', accent: '#D9A668' },
  },
  bar: {
    name: 'Atlas One Bar',
    tagline: 'Barra, mesas, inventario líquido',
    description: 'Bares, cantinas y lounges con control nocturno.',
    accent: '#7C3AED',
    accent2: '#22D3EE',
    accentSoft: '#EFE6FB',
    accentInk: '#4C1D95',
    tint: '#1A0B2E',
    sidebar: { bg: '#0A0418', fg: '#E9D8FD', mute: '#7A6BA0', activeBg: '#1A0B2E', accent: '#22D3EE' },
  },
  services: {
    name: 'Atlas One Services',
    tagline: 'Órdenes y seguimiento técnico',
    description: 'Talleres, mantenimiento y servicios técnicos.',
    accent: '#0E7C5C',
    accent2: '#0EA5E9',
    accentSoft: '#E2F1EB',
    accentInk: '#063D2C',
    tint: '#E8F1ED',
    sidebar: { bg: '#0E1614', fg: '#D8E5DF', mute: '#6E8278', activeBg: '#152620', accent: '#34D399' },
  },
  enterprise: {
    name: 'Atlas One Enterprise',
    tagline: 'Multisucursal e integraciones',
    description: 'Operación avanzada, KPIs ejecutivos y módulos a la medida.',
    accent: '#6D28D9',
    accent2: '#3B82F6',
    accentSoft: '#EDE7FA',
    accentInk: '#3D1798',
    tint: '#0E0817',
    sidebar: { bg: '#08060F', fg: '#E2DAFB', mute: '#7B6EA8', activeBg: '#15102A', accent: '#A78BFA' },
  },
  custom: {
    name: 'Atlas One Custom',
    tagline: 'Configuración a la medida',
    description: 'Constructor de módulos para giros con reglas propias.',
    accent: '#0A0A0A',
    accent2: '#A78BFA',
    accentSoft: '#F0EDE5',
    accentInk: '#0A0A0A',
    tint: '#F2EFE7',
    sidebar: { bg: '#0F0F0F', fg: '#E8E5DD', mute: '#7A7872', activeBg: '#1C1C1C', accent: '#A78BFA' },
  },
} satisfies Record<string, PresetConfig>;

export type PresetKey = keyof typeof PRESETS;

/**
 * Maps backend IndustryType enum values to PRESETS keys.
 * Legacy values (ATLAS_ONE_BEAUTY, ATLAS_ONE_GASTRO) map to v2 equivalents.
 */
export const INDUSTRY_TYPE_TO_PRESET: Record<string, PresetKey> = {
  ATLAS_POS: 'pos',
  ATLAS_POS_BOUTIQUE: 'pos',
  ATLAS_ONE_RETAIL: 'retail',
  ATLAS_ONE_BARBER: 'barber',
  ATLAS_ONE_BEAUTY_WELLNESS: 'beauty_wellness',
  ATLAS_ONE_HEALTH: 'health',
  ATLAS_ONE_RESTAURANT: 'restaurant',
  ATLAS_ONE_CAFE: 'cafe',
  ATLAS_ONE_BAR: 'bar',
  ATLAS_ONE_SERVICES: 'services',
  ATLAS_ONE_ENTERPRISE: 'enterprise',
  CUSTOM: 'custom',
  // Legacy taxonomy v1
  ATLAS_ONE_BEAUTY: 'beauty_wellness',
  ATLAS_ONE_GASTRO: 'restaurant',
};

export function presetFor(industryType: string | null | undefined): PresetConfig {
  if (!industryType) return PRESETS.pos;
  const key = INDUSTRY_TYPE_TO_PRESET[industryType];
  return PRESETS[key] || PRESETS.pos;
}
