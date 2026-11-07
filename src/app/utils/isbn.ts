/** An ISBN-13 barcode (EAN-13 starting 978/979) with a correct check digit. */
export function isIsbn13(code: string): boolean {
  if (!/^97[89]\d{10}$/.test(code)) return false;
  const sum = [...code].reduce((total, digit, i) => total + Number(digit) * (i % 2 === 0 ? 1 : 3), 0);
  return sum % 10 === 0;
}
