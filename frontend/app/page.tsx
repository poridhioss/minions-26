'use client';

import { useState } from 'react';
import PredictionForm from '@/components/PredictionForm';
import ResultCard from '@/components/ResultCard';

export default function Home() {
  const [prediction, setPrediction] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async (formData: Record<string, string | number>) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Prediction failed');
      }

      const data = await response.json();
      const priceMatch = data.predicted_house_price.match(/\$([\d,]+\.?\d*)/);
      setPrediction(priceMatch ? parseFloat(priceMatch[1].replace(/,/g, '')) : 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-900 mb-4">
            🏠 House Price Predictor
          </h1>
          <p className="text-xl text-gray-600">
            Using advanced machine learning to estimate property values
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {/* Form Section */}
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Enter Property Details</h2>
            <PredictionForm onSubmit={handlePredict} loading={loading} />
          </div>

          {/* Result Section */}
          <div className="flex flex-col justify-center">
            {error && (
              <div className="bg-red-50 border-2 border-red-200 rounded-2xl p-6 mb-4">
                <p className="text-red-800 font-semibold">❌ Error: {error}</p>
              </div>
            )}
            {prediction !== null && (
              <ResultCard prediction={prediction} />
            )}
            {!prediction && !error && !loading && (
              <div className="bg-indigo-50 border-2 border-indigo-200 rounded-2xl p-8 text-center">
                <p className="text-indigo-700 text-lg">
                  📊 Enter property details and submit to see the predicted price
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Info Section */}
        <div className="mt-16 max-w-4xl mx-auto">
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">📈 How It Works</h2>
            <div className="grid md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="text-4xl mb-2">1️⃣</div>
                <h3 className="font-bold text-gray-900">Input Data</h3>
                <p className="text-gray-600 text-sm mt-2">Provide property information</p>
              </div>
              <div className="text-center">
                <div className="text-4xl mb-2">2️⃣</div>
                <h3 className="font-bold text-gray-900">ML Model</h3>
                <p className="text-gray-600 text-sm mt-2">Process with trained algorithm</p>
              </div>
              <div className="text-center">
                <div className="text-4xl mb-2">3️⃣</div>
                <h3 className="font-bold text-gray-900">Price Prediction</h3>
                <p className="text-gray-600 text-sm mt-2">Get accurate price estimate</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
