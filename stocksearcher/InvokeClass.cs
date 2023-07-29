using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace stocksearcher
{
    public static class InvokeClass
    {
        public static void InvokeForm(this Form form, Action func)
        {
            if (form.InvokeRequired)
            {
                form.Invoke(func);
            }
            else
            {
                func();
            }
        }
        public static T InvokeForm<T>(this Form form, Func<T> func)
        {
            if (form.InvokeRequired)
            {
                return (T)form.Invoke(func);
            }
            else
            {
                return func();
            }
        }
        public static void InvokeControl(this Control ctl, Action func)
        {
            if (ctl.InvokeRequired)
            {
                ctl.Invoke(func);
            }
            else
            {
                func();
            }
        }
        public static T InvokeControl<T>(this Control ctl, Func<T> func)
        {
            if (ctl.InvokeRequired)
            {
                return (T)ctl.Invoke(func);
            }
            else
            {
                return func();
            }
        }
    }
}
