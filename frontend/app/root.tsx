import type {
  MetaFunction,
  LinksFunction,
  LoaderFunctionArgs,
  TypedResponse,
} from '@remix-run/node'
import type { Theme } from '#app/utils/hooks/use-theme'
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLoaderData,
} from '@remix-run/react'
import { useChangeLanguage } from 'remix-i18next/react'
import { AuthenticityTokenProvider } from 'remix-utils/csrf/react'
import { HoneypotProvider } from 'remix-utils/honeypot/react'
// Old auth system (authenticator, prisma direct user fetch) is being replaced by Clerk.
// Remove or comment out imports related to the old auth system if they are no longer needed.
// import { authenticator } from '#app/modules/auth/auth.server' 
// import { prisma } from '#app/utils/db.server'
import { useNonce } from '#app/utils/hooks/use-nonce'
import { getHints } from '#app/utils/hooks/use-hints'
import { getTheme, useTheme } from '#app/utils/hooks/use-theme'
import { getToastSession } from '#app/utils/toast.server'
import { csrf } from '#app/utils/csrf.server'
import { honeypot } from '#app/utils/honeypot.server'
import { combineHeaders, getDomainUrl } from '#app/utils/misc.server'
import { siteConfig } from '#app/utils/constants/brand'
import { useToast } from '#app/components/toaster'
import { Toaster } from '#app/components/ui/sonner'
import { ClientHintCheck } from '#app/components/misc/client-hints'
// GenericErrorBoundary might be replaced or supplemented by ClerkCatchBoundary
// import { GenericErrorBoundary } from '#app/components/misc/error-boundary' 
import i18nServer, { localeCookie } from '#app/modules/i18n/i18n.server'

// Clerk imports
import { ClerkApp } from '@clerk/remix' // Adjusted import
import { rootAuthLoader } from '@clerk/remix/ssr.server'
import { ENV } from '#app/utils/env.server' // Your ENV object
import { useRouteError, isRouteErrorResponse } from '@remix-run/react'; // Added for ErrorBoundary


import RootCSS from './root.css?url'

export const handle = { i18n: ['translation'] }

export const meta: MetaFunction<typeof loader> = ({ data }) => {
  // `data` will now include properties from rootAuthLoader and your custom data
  const title = data?.siteConfig?.siteTitle || siteConfig.siteTitle;
  return [
    { title: title },
    { name: 'description', content: siteConfig.siteDescription },
  ]
}

export const links: LinksFunction = () => {
  return [{ rel: 'stylesheet', href: RootCSS }]
}

export type LoaderData = Awaited<ReturnType<typeof loader>>;

// New loader function using Clerk's rootAuthLoader
export const loader = async (args: LoaderFunctionArgs) => {
  return rootAuthLoader(args, async ({ request }) => {
    // This inner callback is for server-side configuration and data loading.
    // It runs AFTER Clerk has handled initial auth state.
    // You can access auth state here using getAuth(args).
    const { CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY } = ENV;

    // Load your application-specific data here.
    // This data will be merged with Clerk's auth state.
    const locale = await i18nServer.getLocale(request);
    const { toast, headers: toastHeaders } = await getToastSession(request);
    const [csrfToken, csrfCookieHeader] = await csrf.commitToken();
    
    // You might want to fetch additional user profile information from your local DB
    // using the Clerk user ID if needed. Example:
    // const { userId: clerkUserId } = await getAuth(args);
    // let localUser = null;
    // if (clerkUserId) {
    //   localUser = await prisma.user.findUnique({ where: { clerkUserId } });
    // }

    return {
      // Clerk keys for server-side functions.
      // publishableKey is often not needed here if it's in ENV for client-side.
      // secretKey is crucial for server-side.
      // However, rootAuthLoader typically infers these from ENV if set up correctly.
      // The main purpose here is to return *additional* data.
      // Let's ensure ENV for client is passed if needed.
      ENV: { CLERK_PUBLISHABLE_KEY }, // Only what's safe for client
      
      // Your application-specific data:
      locale,
      toast,
      csrfToken,
      honeypotProps: honeypot.getInputProps(),
      requestInfo: {
        hints: getHints(request),
        origin: getDomainUrl(request),
        path: new URL(request.url).pathname,
        userPrefs: { theme: getTheme(request) },
      },
      siteConfig: { siteTitle: siteConfig.siteTitle }, // Example: pass site title
      // localUser, // Your local user profile data
      
      // IMPORTANT: Any headers you need to set on the response
      // must be returned in a `responseHeaders` object.
      // `rootAuthLoader` will merge these with its own headers.
      responseHeaders: combineHeaders(
        { 'Set-Cookie': await localeCookie.serialize(locale) },
        toastHeaders,
        csrfCookieHeader ? { 'Set-Cookie': csrfCookieHeader } : null,
      ),
    };
  }, { loadUser: true }); // loadUser: true will fetch user data via Clerk
};

// Document component remains the same
function Document({
  children,
  nonce,
  lang = 'en',
  dir = 'ltr',
  theme = 'light',
}: {
  children: React.ReactNode
  nonce: string
  lang?: string
  dir?: 'ltr' | 'rtl'
  theme?: Theme
}) {
  return (
    <html
      lang={lang}
      dir={dir}
      className={`${theme} overflow-x-hidden`}
      style={{ colorScheme: theme }}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <ClientHintCheck nonce={nonce} />
        <Meta />
        <Links />
      </head>
      <body className="h-auto w-full">
        {children}
        <ScrollRestoration nonce={nonce} />
        <Scripts nonce={nonce} />
        <Toaster closeButton position="bottom-center" theme={theme} />
      </body>
    </html>
  )
}

// App component wrapped with ClerkApp
export default function App() {
  const data = useLoaderData<typeof loader>(); // Data from the new Clerk-aware loader
  const nonce = useNonce();
  const theme = useTheme();

  // Update i18n instance language
  useChangeLanguage(data.locale);

  // Render toast (if any)
  useToast(data.toast);

  return (
    // Document is now the root, ClerkApp HOF wraps the App component
    <Document nonce={nonce} theme={theme} lang={data.locale ?? 'en'}>
      {/* CSRF and Honeypot providers are kept, using data from the loader */}
      <AuthenticityTokenProvider token={data.csrfToken}>
        <HoneypotProvider {...data.honeypotProps}>
          <Outlet />
        </HoneypotProvider>
      </AuthenticityTokenProvider>
    </Document>
  );
}

// Default export is now the App component wrapped by ClerkApp HOF
export default ClerkApp(App);

// Standard Remix ErrorBoundary
export function ErrorBoundary() {
  const error = useRouteError();
  let errorTitle = "Error";
  let errorMessage = "An unexpected error occurred.";

  if (isRouteErrorResponse(error)) {
    errorTitle = `${error.status} ${error.statusText}`;
    errorMessage = error.data?.message || error.data || "Sorry, something went wrong.";
  } else if (error instanceof Error) {
    errorMessage = error.message;
  }
  
  // Use a simplified HTML structure for the error page
  return (
    <html lang="en">
      <head>
        <title>{errorTitle}</title>
        <Meta /> {/* Basic meta tags */}
        <Links /> {/* Stylesheets */}
      </head>
      <body>
        <div style={{ padding: '20px', textAlign: 'center', fontFamily: 'sans-serif' }}>
          <h1>{errorTitle}</h1>
          <p>{errorMessage}</p>
          <p><a href="/">Go to Homepage</a></p>
        </div>
        <Scripts />
      </body>
    </html>
  );
}

// Old ClerkCatchBoundary export is removed
// export const CatchBoundary = ClerkCatchBoundary;
