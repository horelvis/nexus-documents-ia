import type { LoaderFunctionArgs } from "@remix-run/node";
import { redirect } from "@remix-run/node";
import { UserProfile } from "@clerk/remix";
import { getAuth } from "@clerk/remix/ssr.server";

// Define SIGN_IN_PATH, or import it if defined globally
const SIGN_IN_PATH = "/auth/sign-in"; 

export const loader = async (args: LoaderFunctionArgs) => {
  const { userId, sessionId } = await getAuth(args);
  if (!userId || !sessionId) {
    // User is not authenticated, redirect to sign-in page
    const params = new URLSearchParams();
    // Optional: Add a redirect_url if your sign-in page supports it
    // params.set("redirect_url", new URL(args.request.url).pathname);
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`);
  }
  return {}; // Return empty object or any necessary data
};

export default function UserProfilePage() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: '2rem', minHeight: 'calc(100vh - 4rem)' /* Adjust based on header/footer */ }}>
      <UserProfile path="/user-profile" routing="path" />
    </div>
  );
}
