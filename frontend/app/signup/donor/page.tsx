import { SignupForm } from "@/components/ui/signup-form";

export default function SignupDonorPage() {
  return (
    <SignupForm
      role="donor"
      accentClass="text-white"
      title="Sign up as donor"
      blurb="Your coordinator will link your account to your existing donor record. After that you'll see the patients you donate to and your donation history."
    />
  );
}
