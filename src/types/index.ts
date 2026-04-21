export interface Photo {
  id: string;
  url: string;
  caption: string;
  date: string;
}

export interface TravelLocation {
  id: string;
  city: string;
  country: string;
  countryCode: string; // ISO 3166-1 numeric for world-atlas topojson
  coordinates: [number, number]; // [longitude, latitude]
  photos: Photo[];
  visitDate: string;
  description: string;
  continent: Continent;
}

export type Continent = 'All' | 'Asia' | 'Europe' | 'Americas' | 'Africa' | 'Oceania';
