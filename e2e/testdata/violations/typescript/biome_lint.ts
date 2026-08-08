export function greeting(name: string): string {
  const unsafe: any = name;
  return unsafe;
}
