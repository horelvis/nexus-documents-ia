import { SignIn } from "@clerk/remix";

export default function SignInPage() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <SignIn routing="path" path="/auth/sign-in" signUpUrl="/auth/sign-up" redirectUrl="/dashboard" />
    </div>
  );
}
