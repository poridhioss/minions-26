'use client';

interface ResultCardProps {
  prediction: number;
}

export default function ResultCard({ prediction }: ResultCardProps) {
  return (
    <div className="bg-gradient-to-br from-green-50 to-emerald-50 border-2 border-green-300 rounded-2xl p-8 text-center">
      <div className="mb-4 text-6xl">🎉</div>
      <h3 className="text-2xl font-bold text-gray-900 mb-2">Prediction Complete!</h3>
      <div className="bg-white rounded-xl p-6 mb-4">
        <p className="text-gray-600 text-sm mb-2">Estimated House Price</p>
        <p className="text-4xl font-bold text-green-600">
          ${prediction.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
      </div>
      <p className="text-green-700 text-sm">
        ✓ This is an AI-powered estimate based on the provided property data
      </p>
    </div>
  );
}
