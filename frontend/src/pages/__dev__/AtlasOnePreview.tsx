/**
 * Dev-only preview of the Atlas One Design System.
 * Equivalent to system-overview.jsx artboard from the sandbox.
 * Renders ALL primitives + iterates through all 11 presets.
 *
 * Accessible only in development via /__dev__/atlas-one-preview.
 */

import React, { useState } from 'react';
import {
  ATLAS_FONT, ATLAS_MONO, ATLAS_SERIF, N, PRESETS, PresetKey,
  Icon, Wordmark,
  Card, SectionTitle, Badge, Avatar, Button, SearchInput,
  Topbar, Sidebar, SidebarUser, Kpi,
  Sparkline, BarChart, LineChart, Donut,
  LaptopFrame, TabletFrame, PhoneFrame,
  mxn, mxnInt,
} from '../../components/atlas-one';

export default function AtlasOnePreview() {
  const [presetKey, setPresetKey] = useState<PresetKey>('pos');
  const preset = PRESETS[presetKey];

  return (
    <div style={{
      width: '100%',
      minHeight: '100vh',
      background: N.canvas,
      fontFamily: ATLAS_FONT,
      color: N.ink,
      padding: 32,
    }}>
      {/* Preset picker */}
      <div style={{ marginBottom: 32, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <div style={{
          fontFamily: ATLAS_MONO,
          fontSize: 11,
          color: N.muted,
          letterSpacing: 1.4,
          textTransform: 'uppercase',
          width: '100%',
          marginBottom: 8,
        }}>Preset · click to swap</div>
        {Object.entries(PRESETS).map(([k, p]) => (
          <button
            key={k}
            onClick={() => setPresetKey(k as PresetKey)}
            style={{
              padding: '6px 12px',
              borderRadius: 7,
              border: `1px solid ${k === presetKey ? p.accent : N.line}`,
              background: k === presetKey ? p.accentSoft : N.card,
              color: N.ink,
              fontFamily: ATLAS_MONO,
              fontSize: 11,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: p.accent }} />
            {p.name}
          </button>
        ))}
      </div>

      {/* Header */}
      <div style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <Wordmark color={N.ink} accent={preset.accent} size={20} sub="Sistema visual v1 · dev preview" />
          <h1 style={{
            fontFamily: ATLAS_SERIF,
            fontSize: 42,
            fontWeight: 500,
            letterSpacing: -1,
            marginTop: 18,
            marginBottom: 0,
          }}>Un solo software. Once configuraciones.</h1>
        </div>
        <div style={{ fontFamily: ATLAS_MONO, fontSize: 11, color: N.muted, letterSpacing: 0.6 }}>
          v 1.0 · ATLAS-ONE · DEV ONLY
        </div>
      </div>

      {/* Sidebar + content side-by-side */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 32 }}>
        <Sidebar
          preset={preset}
          active="Punto de venta"
          width={232}
          items={[
            { header: 'Operación' },
            { icon: Icon.cart, label: 'Punto de venta' },
            { icon: Icon.receipt, label: 'Caja', badge: 3 },
            { icon: Icon.pkg, label: 'Productos' },
            { icon: Icon.users, label: 'Clientes' },
            { header: 'Analítica' },
            { icon: Icon.chart, label: 'Reportes' },
            { icon: Icon.branch, label: 'Sucursales' },
          ]}
          footer={<SidebarUser preset={preset} name="Ana Lozano" role="Cajera" branch="MX-01" />}
        />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Topbar
            title="Panel de operación"
            sub={`${preset.name.toUpperCase()} · ${preset.tagline.toUpperCase()}`}
            right={
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <SearchInput width={280} />
                <Icon.bell size={18} color={N.muted} />
                <Button label="Nueva venta" kind="primary" preset={preset} icon={Icon.plus} />
              </div>
            }
          />

          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
            <Kpi label="Ventas de hoy" value={mxnInt(48230)} delta="+12.4%" trend={[3,4,5,4,6,7,8,7,9,11,10,12]} accent={preset.accent} />
            <Kpi label="Tickets" value={143} delta="+8.1%" trend={[2,3,4,4,5,6,7,6,8,9,10,11]} accent={preset.accent} />
            <Kpi label="Ticket promedio" value={mxn(186.50)} delta="+3.2%" sub="Sin propina" />
            <Kpi label="Productos vendidos" value="412" sub="3 abiertos · 2 cerrados" />
          </div>

          {/* Charts row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 18 }}>
            <Card>
              <SectionTitle>Ventas por hora</SectionTitle>
              <BarChart
                color={preset.accent}
                data={[
                  { label: 'L', value: 4 }, { label: 'M', value: 6 }, { label: 'M', value: 5 },
                  { label: 'J', value: 8 }, { label: 'V', value: 11, highlight: true },
                  { label: 'S', value: 14, highlight: true }, { label: 'D', value: 7 },
                ]}
                width={360} height={140}
              />
            </Card>
            <Card>
              <SectionTitle>Capacidad</SectionTitle>
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 12 }}>
                <Donut value={0.78} label="Capacidad" color={preset.accent} />
              </div>
            </Card>
          </div>

          {/* Buttons + Badges */}
          <Card>
            <SectionTitle>Botones · estilos</SectionTitle>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
              <Button label="Cobrar $1,240" kind="primary" preset={preset} icon={Icon.arrowRight} />
              <Button label="Cancelar" kind="secondary" />
              <Button label="+ Nuevo" kind="accent" preset={preset} />
              <Button label="Editar" kind="ghost" size="sm" icon={Icon.cog} />
            </div>
            <SectionTitle>Badges</SectionTitle>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <Badge color="#0E8A4E" soft="#E3F4EA" dot>Caja abierta</Badge>
              <Badge color="#B43E2E" soft="#FBE7E1" dot>Stock crítico</Badge>
              <Badge color="#9A6610" soft="#FBEFD7" dot>Pendiente</Badge>
              <Badge color="#C8571F" soft="#E5ECFB" dot>En cocina</Badge>
              <Badge color="#6B6B66" soft={N.chip}>SKU-7821</Badge>
            </div>
          </Card>

          {/* Avatars */}
          <Card>
            <SectionTitle>Avatares</SectionTitle>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Avatar name="Ana Lozano" />
              <Avatar name="Pedro Martinez" color={preset.accentSoft} />
              <Avatar name="Lourdes Toledo" size={40} color={preset.accent2} />
              <Avatar name="Saúl Mendoza" size={52} color={preset.accent} />
            </div>
          </Card>

          {/* Icon grid */}
          <Card>
            <SectionTitle>Iconografía · stroke 1.6 · 24×24</SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(14, 1fr)', gap: 6 }}>
              {Object.entries(Icon).map(([k, IconCmp]) => (
                <div key={k} title={k} style={{
                  aspectRatio: '1',
                  border: `1px solid ${N.line}`,
                  borderRadius: 7,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: N.body,
                }}>
                  <IconCmp size={18} />
                </div>
              ))}
            </div>
          </Card>

          {/* LineChart */}
          <Card>
            <SectionTitle>Tendencia · doble serie</SectionTitle>
            <LineChart
              series={[
                { values: [3,5,4,7,8,10,9,12,14,13,15,18,17,20,22] },
                { values: [2,3,3,5,6,7,7,9,10,10,12,14,13,16,18] },
              ]}
              color={preset.accent}
              color2={preset.accent2}
              labels={['07','','09','','11','','13','','15','','17','','19','','21']}
              width={620} height={180}
            />
          </Card>

          {/* Sparklines */}
          <Card>
            <SectionTitle>Sparklines (inline en KPI)</SectionTitle>
            <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
              <Sparkline values={[3,4,5,4,6,7,8,7,9,11,10,12,14,13]} color={preset.accent} width={140} height={36} />
              <Sparkline values={[3,4,5,4,6,7,8,7,9,11,10,12,14,13]} color={preset.accent} width={140} height={36} fill />
              <Sparkline values={[12,11,10,11,9,8,9,8,7,6,7,5,4,3]} color="#B43E2E" width={140} height={36} />
            </div>
          </Card>

          {/* Device frames */}
          <Card>
            <SectionTitle>Device frames · marketing artboards</SectionTitle>
            <div style={{ display: 'flex', gap: 24, alignItems: 'flex-end' }}>
              <LaptopFrame width={320}>
                <div style={{ width: '100%', height: '100%', background: preset.tint, padding: 16, fontFamily: ATLAS_FONT, fontSize: 11 }}>
                  <Wordmark color={preset.accentInk} accent={preset.accent} size={11} sub={preset.tagline} />
                  <div style={{ marginTop: 18, fontFamily: ATLAS_SERIF, fontSize: 18, color: preset.accentInk, letterSpacing: -0.3 }}>
                    Dashboard {preset.name}
                  </div>
                </div>
              </LaptopFrame>
              <TabletFrame width={220}>
                <div style={{ width: '100%', height: '100%', background: preset.accentSoft, padding: 14, fontFamily: ATLAS_FONT }}>
                  <div style={{ fontFamily: ATLAS_MONO, fontSize: 9, color: preset.accentInk, letterSpacing: 0.8, textTransform: 'uppercase' }}>{preset.name}</div>
                  <div style={{ fontFamily: ATLAS_SERIF, fontSize: 14, color: preset.accentInk, marginTop: 6, letterSpacing: -0.2 }}>Touch / Mostrador</div>
                </div>
              </TabletFrame>
              <PhoneFrame width={140}>
                <div style={{ width: '100%', height: '100%', background: preset.tint, padding: 14, fontFamily: ATLAS_FONT, fontSize: 10 }}>
                  <div style={{ color: preset.accentInk }}>Hola, Ana</div>
                  <div style={{ fontFamily: ATLAS_MONO, fontSize: 8, color: N.muted, marginTop: 4 }}>{preset.name.toUpperCase()}</div>
                </div>
              </PhoneFrame>
            </div>
          </Card>

          {/* Typography */}
          <Card>
            <SectionTitle>Tipografía · IBM Plex</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <div style={{ fontFamily: ATLAS_SERIF, fontSize: 36, fontWeight: 500, letterSpacing: -0.8 }}>Plex Serif · headlines</div>
                <div style={{ fontFamily: ATLAS_MONO, fontSize: 10, color: N.muted, marginTop: 4 }}>SERIF 500 · 32 / 38 / 44 · LETTER -0.8</div>
              </div>
              <div>
                <div style={{ fontFamily: ATLAS_FONT, fontSize: 22, fontWeight: 600, letterSpacing: -0.3 }}>Plex Sans · section titles</div>
                <div style={{ fontFamily: ATLAS_FONT, fontSize: 14, color: N.body, marginTop: 4, lineHeight: 1.5 }}>Plex Sans 400 · body text.</div>
              </div>
              <div>
                <div style={{ fontFamily: ATLAS_MONO, fontSize: 13, fontWeight: 500, color: N.ink, letterSpacing: 0.4 }}>PLEX MONO · MÉTRICAS Y CÓDIGOS</div>
                <div style={{ fontFamily: ATLAS_MONO, fontSize: 13, color: N.body, marginTop: 4 }}>$ 12,480.50 · SKU-7821 · 09:41</div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
