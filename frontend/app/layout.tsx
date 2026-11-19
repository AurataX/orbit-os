import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./styles.css";

export const metadata: Metadata = {
  title: "ORBIT-OS · Simulation Console",
  description: "A live operating systems lab for heterogeneous resource scheduling and deterministic replay.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
