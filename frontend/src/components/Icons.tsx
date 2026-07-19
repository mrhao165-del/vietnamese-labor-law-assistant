type Props = {
  className?: string;
};

export function FileText({ className }: Props) { return <span className={`material-symbols-outlined ${className ?? ''}`}>description</span>; }
export function MenuBook({ className }: Props) { return <span className={`material-symbols-outlined ${className ?? ''}`}>menu_book</span>; }
export function ErrorOutline({ className }: Props) { return <span className={`material-symbols-outlined ${className ?? ''}`}>error</span>; }
export function ShieldCheck({ className }: Props) { return <span className={`material-symbols-outlined fill ${className ?? ''}`}>verified</span>; }
export function Warning({ className }: Props) { return <span className={`material-symbols-outlined fill ${className ?? ''}`}>warning</span>; }
export function Info({ className }: Props) { return <span className={`material-symbols-outlined ${className ?? ''}`}>info</span>; }
