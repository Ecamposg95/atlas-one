/**
 * Atlas One design tokens
 * Source: C:\Users\ecamp\Devs\Atlas Brain\AtlasONE\ATLAS ONE\system.jsx (lines 11-155)
 */

export const ATLAS_FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', Arial, sans-serif";
export const ATLAS_MONO = "'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace";
export const ATLAS_SERIF = "'Inter', system-ui, sans-serif";

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
    accent: '#EB6725',
    accent2: '#FA9360',
    accentSoft: '#EEF3FE',
    accentInk: '#8A421E',
    tint: '#EDF2FB',
    sidebar: { bg: '#26170F', fg: '#E6EEFB', mute: '#7C8AA8', activeBg: '#40271A', accent: '#FA9360' },
  },
  retail: {
    name: 'Atlas One Retail',
    tagline: 'Inventario que cuadra',
    description: 'Productos, SKU, stock y mostrador para tiendas con inventario exigente.',
    accent: '#8F370B',
    accent2: '#D44B06',
    accentSoft: '#E6F0FB',
    accentInk: '#6B2908',
    tint: '#E8F1FB',
    sidebar: { bg: '#26130A', fg: '#F6E5DC', mute: '#6E80A0', activeBg: '#482310', accent: '#EE6622' },
  },
  barber: {
    name: 'Atlas One Barber',
    tagline: 'Silla, navaja y agenda',
    description: 'Agenda por barbero, servicios, comisiones y clientes frecuentes.',
    accent: '#76310F',
    accent2: '#D35D22',
    accentSoft: '#EBF2F1',
    accentInk: '#4E1E06',
    tint: '#EEF1F0',
    sidebar: { bg: '#0B0B0C', fg: '#E8E6E2', mute: '#7A7872', activeBg: '#171716', accent: '#D35D22' },
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
    accent: '#9F3E0E',
    accent2: '#FCA77D',
    accentSoft: '#F5E8E1',
    accentInk: '#5E2407',
    tint: '#F3EBE7',
    sidebar: { bg: '#23150E', fg: '#F5E8E1', mute: '#6E8C8E', activeBg: '#3A2216', accent: '#EA8D5E' },
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
    accent: '#EA580C',
    accent2: '#EE6622',
    accentSoft: '#EFE6FB',
    accentInk: '#95451D',
    tint: '#2E170B',
    sidebar: { bg: '#0A0418', fg: '#FDE4D8', mute: '#7A6BA0', activeBg: '#2E170B', accent: '#EE6622' },
  },
  services: {
    name: 'Atlas One Services',
    tagline: 'Órdenes y seguimiento técnico',
    description: 'Talleres, mantenimiento y servicios técnicos.',
    accent: '#0E7C5C',
    accent2: '#E9570E',
    accentSoft: '#E2F1EB',
    accentInk: '#063D2C',
    tint: '#E8F1ED',
    sidebar: { bg: '#0E1614', fg: '#D8E5DF', mute: '#6E8278', activeBg: '#152620', accent: '#34D399' },
  },
  enterprise: {
    name: 'Atlas One Enterprise',
    tagline: 'Multisucursal e integraciones',
    description: 'Operación avanzada, KPIs ejecutivos y módulos a la medida.',
    accent: '#D96328',
    accent2: '#F6793B',
    accentSoft: '#EDE7FA',
    accentInk: '#984217',
    tint: '#170D08',
    sidebar: { bg: '#08060F', fg: '#FBE5DA', mute: '#A8816E', activeBg: '#2A1910', accent: '#FFA14A' },
  },
  custom: {
    name: 'Atlas One Custom',
    tagline: 'Configuración a la medida',
    description: 'Constructor de módulos para giros con reglas propias.',
    accent: '#0A0A0A',
    accent2: '#FFA14A',
    accentSoft: '#F0EDE5',
    accentInk: '#0A0A0A',
    tint: '#F2EFE7',
    sidebar: { bg: '#0F0F0F', fg: '#E8E5DD', mute: '#7A7872', activeBg: '#1C1C1C', accent: '#FFA14A' },
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
