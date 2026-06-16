import { useSettings } from '../context/SettingsContext'

const MIN_H = 300
const MAX_H = 2000
const STEP = 50

export default function Settings() {
  const { trendChartHeight, set, reset } = useSettings()

  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-xl font-semibold text-white mb-6">Ayarlar</h1>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-6">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Trend Grafik</h2>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm text-white">Grafik Yüksekliği</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={MIN_H}
                max={MAX_H}
                step={STEP}
                value={trendChartHeight}
                onChange={e => {
                  const v = Number(e.target.value)
                  if (v >= MIN_H && v <= MAX_H) set('trendChartHeight', v)
                }}
                className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white text-right focus:outline-none focus:border-blue-500"
              />
              <span className="text-sm text-gray-400">px</span>
            </div>
          </div>

          <input
            type="range"
            min={MIN_H}
            max={MAX_H}
            step={STEP}
            value={trendChartHeight}
            onChange={e => set('trendChartHeight', Number(e.target.value))}
            className="w-full accent-blue-500"
          />

          <div className="flex justify-between text-xs text-gray-500">
            <span>{MIN_H}px</span>
            <span className="text-gray-400">Seçili: <span className="text-white font-medium">{trendChartHeight}px</span></span>
            <span>{MAX_H}px</span>
          </div>
        </div>
      </div>

      <button
        onClick={reset}
        className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
      >
        Varsayılanlara Sıfırla
      </button>
    </div>
  )
}
