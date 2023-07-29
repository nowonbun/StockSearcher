using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using NPOI.HSSF;
using NPOI.HSSF.UserModel;
using NPOI.SS.UserModel;

namespace stocksearcher
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            comboBox1.SelectedItem = comboBox1.Items[0];
        }

        private void button1_Click(object sender, EventArgs e)
        {
            DialogResult dr = openFileDialog1.ShowDialog();
            if (dr == DialogResult.OK)
            {
                toolStripProgressBar1.Visible = true;
                this.textBox1.Text = openFileDialog1.FileNames.FirstOrDefault();
                ThreadPool.QueueUserWorkItem((_) =>
                {
                    if (File.Exists(this.textBox1.Text))
                    {
                        this.button2.InvokeControl(() =>
                        {
                            this.button2.Enabled = true;
                        });
                    }
                    this.statusStrip1.InvokeControl(() =>
                    {
                        this.toolStripProgressBar1.Visible = false;
                    });
                });
            }
        }

        private String GetCellValue(ICell cell)
        {
            switch (cell.CellType)
            {
                case CellType.String:
                    return cell.StringCellValue;
                case CellType.Numeric:
                    return cell.NumericCellValue.ToString();
            }
            return null;
        }

        private void button2_Click(object sender, EventArgs e)
        {
            toolStripProgressBar1.Visible = true;
            this.button1.Enabled = false;
            this.button2.Enabled = false;
            ThreadPool.QueueUserWorkItem((_) =>
            {
                if (File.Exists(this.textBox1.Text))
                {
                    IWorkbook workbook;
                    using (var stream = new FileStream(this.textBox1.Text, FileMode.Open, FileAccess.Read))
                    {
                        workbook = new HSSFWorkbook(stream);
                    }
                    var sheet = workbook.GetSheetAt(0);
                    using (var context = new stocksearcherEntities1())
                    {
                        var stocklist = context.stocklist.Where(x => x.isuse.HasValue).ToList();
                        var stockcodelist = context.stocktype.Where(x => x.isuse.HasValue).ToList();
                        var type17list = context.type17.Where(x => x.isuse.HasValue).ToList();
                        var type33list = context.type33.Where(x => x.isuse.HasValue).ToList();
                        var typescalelist = context.typescale.Where(x => x.isuse.HasValue).ToList();
                        for (int i = 1; true; i++)
                        {
                            var row = sheet.GetRow(i);
                            if(row == null)
                            {
                                break;
                            }
                            var cell = row.GetCell(0);
                            if (cell == null || String.IsNullOrEmpty(GetCellValue(cell)))
                            {
                                break;
                            }
                            var stock = new stocklist();
                            stock.date = GetCellValue(row.GetCell(0));
                            stock.code = GetCellValue(row.GetCell(1));
                            stock.name = GetCellValue(row.GetCell(2));
                            stock.isuse = true;

                            var stockcodename = GetCellValue(row.GetCell(3));
                            var type33code = GetCellValue(row.GetCell(4));
                            var type33name = GetCellValue(row.GetCell(5));
                            var type17code = GetCellValue(row.GetCell(6));
                            var type17name = GetCellValue(row.GetCell(7));
                            var typescalecode = GetCellValue(row.GetCell(8));
                            var typescalename = GetCellValue(row.GetCell(9));

                            if (stocklist.Where(x => String.Equals(x.code, stock.code, StringComparison.OrdinalIgnoreCase)).Any())
                            {
                                continue;
                            }

                            var stockcode = stockcodelist.Where(x => String.Equals(x.stocktype1, stockcodename, StringComparison.OrdinalIgnoreCase)).FirstOrDefault();
                            if (stockcode == null)
                            {
                                stockcode = new stocktype();
                                stockcode.stocktype1 = stockcodename;
                                stockcode.isuse = true;
                                stockcodelist.Add(stockcode);
                            }
                            stock.stocktype = stockcode;

                            var type33 = type33list.Where(x => String.Equals(x.type33code, type33code, StringComparison.OrdinalIgnoreCase)).FirstOrDefault();
                            if (type33 == null)
                            {
                                type33 = new type33();
                                type33.type33code = type33code;
                                type33.type33name = type33name;
                                type33.isuse = true;
                                type33list.Add(type33);
                            }
                            stock.type33 = type33;

                            var type17 = type17list.Where(x => String.Equals(x.type17code, type17code, StringComparison.OrdinalIgnoreCase)).FirstOrDefault();
                            if (type17 == null)
                            {
                                type17 = new type17();
                                type17.type17code = type17code;
                                type17.type17name = type17name;
                                type17.isuse = true;
                                type17list.Add(type17);
                            }
                            stock.type17 = type17;

                            var typescale = typescalelist.Where(x => String.Equals(x.typescalecode, typescalecode, StringComparison.OrdinalIgnoreCase)).FirstOrDefault();
                            if (typescale == null)
                            {
                                typescale = new typescale();
                                typescale.typescalecode = typescalecode;
                                typescale.typescalename = typescalename;
                                typescale.isuse = true;
                                typescalelist.Add(typescale);
                            }
                            stock.typescale = typescale;
                            context.stocklist.Add(stock);
                        }

                        context.SaveChanges();

                        this.button1.InvokeControl(() =>
                        {
                            this.button1.Enabled = true;
                        });
                        this.button2.InvokeControl(() =>
                        {
                            this.button2.Enabled = true;
                        });
                        this.statusStrip1.InvokeControl(() =>
                        {
                            this.toolStripProgressBar1.Visible = false;
                        });
                    }
                }
            });
        }

        private void button4_Click(object sender, EventArgs e)
        {
            
        }
    }
}
