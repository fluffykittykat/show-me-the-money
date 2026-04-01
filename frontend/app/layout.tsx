import type { Metadata } from 'next';
import './globals.css';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import IngestionBanner from '@/components/IngestionBanner';
import GlobalChat from '@/components/GlobalChat';

export const metadata: Metadata = {
  title: 'Follow the Money — Political Intelligence Platform',
  description:
    'Every dollar tells a story. Every connection reveals the truth. Track political finance, lobbying, and legislative activity.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <Header />
        <IngestionBanner />
        <main className="flex-1">{children}</main>
        <Footer />
        <GlobalChat />
      </body>
    </html>
  );
}
