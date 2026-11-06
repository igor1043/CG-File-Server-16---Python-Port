/* Only our tagged bank-mail bodies contain these bounded amount tokens.
 * Use the same native formatter as ION_Localization.LocalizeCurrencyWithType.
 * Currency slots may be renamed by the installed language DB; never map them
 * to hard-coded dollars/euros/pounds or change accounting units here. */
typedef struct CareerMoneyString {char *begin,*end,*capacity;const char *allocator;} CareerMoneyString;

static int career_mail_money(int slot,int amount,char *out,size_t capacity)
{
    uintptr_t localizer=0,vtable=0,method=0;CareerMoneyString text;
    size_t length;int ok=0;
    if(slot<0 || slot>2 || !read_card_scope((uintptr_t)g_module_base+0x351a0b0,&localizer,8)
        || !read_card_scope(localizer,&vtable,8) || vtable!=(uintptr_t)g_module_base+0x21993f0
        || !read_card_scope(vtable+0x68,&method,8) || method!=(uintptr_t)g_module_base+0x3d33bc0
        || memcmp(g_module_base+0x3d33bc0,"\x48\x89\x5c\x24\x08",5))return 0;
    text.begin=text.end=(char *)g_module_base+0x34a6800;text.capacity=text.begin+1;text.allocator="EASTL basic_string";
    ((void (*)(void *,CareerMoneyString *,unsigned char,int,int))method)((void *)localizer,&text,0,amount,slot);
    length=(uintptr_t)text.end>=(uintptr_t)text.begin?(size_t)(text.end-text.begin):SIZE_MAX;
    if(length<capacity && is_readable_range(text.begin,length+1) && !text.begin[length]){
        memcpy(out,text.begin,length+1);ok=1;
    }
    if((uintptr_t)text.capacity>(uintptr_t)text.begin+1 && text.begin)
        ((void (*)(void *))(g_module_base+0x489b140))(text.begin);
    return ok;
}

static void career_mail_currency(const char *body,char *out,size_t capacity)
{
    size_t used=0;const char *cursor=body;
    while(*cursor && used+1<capacity){
        if(!strncmp(cursor,"{{S16M:",7) && cursor[7]>='0' && cursor[7]<='2' && cursor[8]==':'){
            const char *end=cursor+9;unsigned amount=0;size_t digits=0;char formatted[192];
            while(*end>='0' && *end<='9' && digits<10){
                if(amount>214748364u || (amount==214748364u && *end>'7'))break;
                amount=amount*10+(unsigned)(*end++-'0');++digits;
            }
            if(digits && end[0]=='}' && end[1]=='}'){
                size_t n;
                if(!career_mail_money(cursor[7]-'0',(int)amount,formatted,sizeof(formatted)))
                    snprintf(formatted,sizeof(formatted),"%u",amount);
                n=strlen(formatted);if(n>=capacity-used)break;
                memcpy(out+used,formatted,n);used+=n;cursor=end+2;continue;
            }
        }
        out[used++]=*cursor++;
    }
    out[used]=0;
}
