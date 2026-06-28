import type { Dispatch, MouseEvent, RefObject, SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { COLORS, type ChartDataPoint, type TrendSeries } from './constants'

interface TrendChartProps {
  chartContainerRef: RefObject<HTMLDivElement | null>
  selectedCount: number
  isLoading: boolean
  chartData: ChartDataPoint[]
  series: TrendSeries[]
  compareMode: boolean
  annotateMode: boolean
  axisLeftMargin: number
  gridStroke: string
  brushStroke: string
  brushFill: string
  brushIndices: [number, number] | null
  setBrushIndices: Dispatch<SetStateAction<[number, number] | null>>
  annotationLines: { id: number; key: string }[]
  handleMouseMove: (state: Record<string, unknown>) => void
  handleMouseLeave: () => void
  handleChartClick: (state: Record<string, unknown>) => void
  handleContextMenu: (event: MouseEvent) => void
}

export function TrendChart({
  chartContainerRef,
  selectedCount,
  isLoading,
  chartData,
  series,
  compareMode,
  annotateMode,
  axisLeftMargin,
  gridStroke,
  brushStroke,
  brushFill,
  brushIndices,
  setBrushIndices,
  annotationLines,
  handleMouseMove,
  handleMouseLeave,
  handleChartClick,
  handleContextMenu,
}: TrendChartProps) {
  const { t } = useTranslation(['trend', 'common'])

  return (
    <div
      ref={chartContainerRef}
      className="flex-1 bg-surface-raised/40 backdrop-blur-xl border border-white/5 rounded-2xl p-4 flex flex-col"
      style={{ userSelect: 'none' }}
      onContextMenu={handleContextMenu}
    >
      {selectedCount === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          {t('select_from_panel')}
        </div>
      ) : isLoading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          {t('common:loading')}
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          {t('no_data_range')}
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 4, right: 16, left: axisLeftMargin, bottom: 4 }}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              onClick={handleChartClick}
              style={{ cursor: annotateMode ? 'crosshair' : undefined }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
              <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#6b7280' }} interval="preserveStartEnd" />
              {series.map((item, i) => {
                const color = COLORS[i % COLORS.length]

                return (
                  <YAxis
                    key={item.tag_id}
                    yAxisId={`y_${item.tag_id}`}
                    orientation="left"
                    width={50}
                    tick={{ fontSize: 10, fill: color }}
                    tickLine={{ stroke: color }}
                    axisLine={{ stroke: color }}
                    label={{
                      value: item.unit,
                      angle: -90,
                      position: 'insideLeft',
                      fill: color,
                      fontSize: 10,
                      dx: -8,
                    }}
                  />
                )
              })}
              <Tooltip
                cursor={{ stroke: '#f59e0b', strokeWidth: 1, strokeDasharray: '4 2' }}
                contentStyle={{ display: 'none' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
              <Brush
                dataKey="t"
                height={24}
                startIndex={brushIndices ? brushIndices[0] : 0}
                endIndex={brushIndices ? brushIndices[1] : Math.max(0, chartData.length - 1)}
                onChange={(range) => {
                  if (
                    range &&
                    typeof range.startIndex === 'number' &&
                    typeof range.endIndex === 'number'
                  ) {
                    setBrushIndices([range.startIndex, range.endIndex])
                  }
                }}
                stroke={brushStroke}
                fill={brushFill}
                travellerWidth={8}
              />
              {series.map((item, i) => (
                <Line
                  key={item.tag_id}
                  type="monotone"
                  dataKey={item.name}
                  name={item.label ?? item.name}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  yAxisId={`y_${item.tag_id}`}
                />
              ))}
              {compareMode &&
                series.map((item, i) => (
                  <Line
                    key={`prev_${item.tag_id}`}
                    type="monotone"
                    dataKey={`${item.name} ${t('previous_suffix')}`}
                    name={`${item.label ?? item.name} ${t('previous_suffix')}`}
                    stroke={COLORS[i % COLORS.length]}
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                    strokeOpacity={0.6}
                    dot={false}
                    connectNulls
                    yAxisId={`y_${item.tag_id}`}
                  />
                ))}
              {series.length > 0 &&
                annotationLines.map((annotation) => (
                  <ReferenceLine
                    key={annotation.id}
                    x={annotation.key}
                    yAxisId={`y_${series[0].tag_id}`}
                    stroke="#fbbf24"
                    strokeDasharray="2 2"
                    label={{ value: '📌', position: 'top', fontSize: 12 }}
                  />
                ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
