// React 18 does not know the `fetchPriority` prop (React 19 does) and warns about it in
// development, so images set the lowercase `fetchpriority` attribute, which React passes to the
// DOM as it is. Typed here because @types/react only declares the camel-case name.
// After upgrading to React 19, delete this file and write `fetchPriority` again.
import 'react';

declare module 'react' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- must match React's declaration
  interface ImgHTMLAttributes<T> {
    fetchpriority?: 'high' | 'low' | 'auto';
  }
}
