interface GreetingViewProps {
  readonly name: string;
}

export function GreetingView({ name }: GreetingViewProps) {
  return <p>Hello, {name}!</p>;
}
