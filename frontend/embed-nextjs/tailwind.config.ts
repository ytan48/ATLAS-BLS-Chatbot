import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ilBlue: '#13294B',
        ilBlueLight: '#1D58A7',
        ilOrange: '#FF5F05',
        ilAltgeld: '#C84113',
        ilStorm: '#707372',
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
