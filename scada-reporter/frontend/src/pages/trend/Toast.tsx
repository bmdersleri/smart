export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-600 text-gray-200 text-sm px-4 py-3 rounded-xl shadow-xl z-50 flex items-center gap-3">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">
        x
      </button>
    </div>
  )
}
