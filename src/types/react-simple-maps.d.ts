declare module 'react-simple-maps' {
  import type { ComponentType, ReactNode, SVGProps, MouseEvent } from 'react';

  interface ComposableMapProps {
    projection?: string;
    projectionConfig?: Record<string, unknown>;
    width?: number;
    height?: number;
    style?: React.CSSProperties;
    className?: string;
    children?: ReactNode;
  }

  interface ZoomableGroupProps {
    zoom?: number;
    center?: [number, number];
    minZoom?: number;
    maxZoom?: number;
    onMoveStart?: (pos: { coordinates: [number, number]; zoom: number }) => void;
    onMove?: (pos: { x: number; y: number; zoom: number; dragging: boolean }) => void;
    onMoveEnd?: (pos: { coordinates: [number, number]; zoom: number }) => void;
    children?: ReactNode;
  }

  interface GeographiesProps {
    geography: string | object;
    children: (props: { geographies: Geography[] }) => ReactNode;
  }

  interface Geography {
    rsmKey: string;
    id: string;
    type: string;
    properties: Record<string, unknown>;
    geometry: object;
  }

  interface GeographyProps extends SVGProps<SVGPathElement> {
    geography: Geography;
    style?: {
      default?: React.CSSProperties;
      hover?: React.CSSProperties;
      pressed?: React.CSSProperties;
    };
  }

  interface MarkerProps {
    coordinates: [number, number];
    children?: ReactNode;
    onClick?: (event: MouseEvent<SVGGElement>) => void;
    onMouseEnter?: (event: MouseEvent<SVGGElement>) => void;
    onMouseLeave?: (event: MouseEvent<SVGGElement>) => void;
    className?: string;
    style?: React.CSSProperties;
  }

  export const ComposableMap: ComponentType<ComposableMapProps>;
  export const ZoomableGroup: ComponentType<ZoomableGroupProps>;
  export const Geographies: ComponentType<GeographiesProps>;
  export const Geography: ComponentType<GeographyProps>;
  export const Marker: ComponentType<MarkerProps>;
  export const Line: ComponentType<unknown>;
  export const Annotation: ComponentType<unknown>;
  export const Graticule: ComponentType<unknown>;
  export const Sphere: ComponentType<unknown>;
}
