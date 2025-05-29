import { UserButton, SignedIn, SignedOut, RedirectToSignIn } from "@clerk/remix";

export default function TestAuth() {
  return (
    <div>
      <SignedIn>
        <h1>Usuario autenticado </h1>
        <UserButton />
      </SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </div>
  );
}

//