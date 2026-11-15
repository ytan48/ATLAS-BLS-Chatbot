import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ilBlue: '#13294B',
        ilBlueLight: '#1D58A7',
        ilBlue30: '#2F4668',
        ilBlue80: '#B5C8E2',
        ilBlue90: '#E1E7F1',
        ilOrange: '#FF5F05',
        ilAltgeld: '#C84113',
        ilStorm: '#707372',
        ilStorm30: '#474948',
        ilStormLight: '#F4F4F4'
      },
      boxShadow: {
        widget: '0 10px 30px rgba(19, 41, 75, 0.18)'
      }
    }
  },
  plugins: []
};

export default config;
